// SPDX-License-Identifier: GPL-2.0
// Copyright (C) 2021 Unisoc, Inc.
#define pr_fmt(fmt) "sprd-apcpu-dvfs: " fmt

#include "sprd-cpufreq-v2.h"
#include <linux/delay.h>
#include <linux/jiffies.h>
#include <linux/nvmem-consumer.h>
#include <linux/pm_qos.h>
#include <linux/thermal.h>

#define low_check(temp)		((int)(temp) < (int)DVFS_TEMP_LOW_LIMIT)
#define upper_check(temp)	((int)(temp) >= (int)DVFS_TEMP_UPPER_LIMIT)
#define temp_check(temp)	(low_check(temp) || upper_check(temp))

#define ON_BOOST		0
#define OUT_BOOST		1
#define SPRD_CPUFREQ_BOOST_DURATION	(60ul * HZ)
#define SPRD_DVFS_DEBUG_MAGIC		(0x5A)

struct cluster_prop {
	char *name;
	u32 *value;
	void **ops;
};

static struct device *dev;
static struct cluster_info *pclusters;
static unsigned long boot_done_timestamp;

/* SML's signed per-domain boot offset also adjusts the matching SRAM table.
 * It mutates firmware tables in place: never repeat DVFS_INIT at runtime.
 * Units are uV here; SML encodes ceil(mV / 3.125) selector steps.
 * Deliberately narrower than the firmware's +/-100 mV debug range.
 */
static int voltage_offset_uv[3];
static unsigned int voltage_offset_count;
static bool firmware_initialized;
module_param_array(voltage_offset_uv, int, &voltage_offset_count, 0444);
MODULE_PARM_DESC(voltage_offset_uv, "Boot CPU/SRAM offsets in uV, three domains, -50000..25000 in 3125 uV steps");

static int sprd_voltage_flag(u32 *flag)
{
	int i, uv;
	u32 encoded;
	if (voltage_offset_count && voltage_offset_count != 3)
		return -EINVAL;
	*flag &= 0xff;
	for (i = 0; i < ARRAY_SIZE(voltage_offset_uv); i++) {
		uv = voltage_offset_uv[i];
		if (uv < -50000 || uv > 25000 || uv % 3125)
			return -ERANGE;
		if (uv && !of_machine_is_compatible("sprd,ums9621"))
			return -EOPNOTSUPP;
		/* floor here reverses the firmware's ceil, exactly for 3125 uV steps. */
		encoded = abs(uv) / 1000;
		if (uv < 0)
			encoded |= 0x80;
		*flag |= encoded << (8 * (i + 1));
	}
	return 0;
}

/* cluster common interface */
static int sprd_cluster_info(u32 cpu_idx)
{
	struct device_node *cpu_np;
	struct of_phandle_args args;
	int ret, index;

	if (cpu_idx >= nr_cpu_ids)
		return -EINVAL;

	cpu_np = of_cpu_device_node_get(cpu_idx);
	if (!cpu_np)
		return -EINVAL;

	ret = of_parse_phandle_with_args(cpu_np, "sprd,freq-domain",
					 "#freq-domain-cells", 0, &args);
	of_node_put(cpu_np);
	if (ret)
		return -EINVAL;

	index = args.args_count == 1 ? args.args[0] : -EINVAL;
	of_node_put(args.np);
	if (index < 0 || index >= nr_cpu_ids)
		return -EINVAL;

	return index;
}

int sprd_cluster_num(void)
{
	int cpu, index, count = 0;
	for_each_possible_cpu(cpu) {
		index = sprd_cluster_info(cpu);
		if (index < 0)
			return index;
		count = max(count, index + 1);
	}
	return count;
}

static int sprd_cpufreq_boost_judge(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster = policy->driver_data;

	if (time_after(jiffies, boot_done_timestamp)) {
		cluster->boost_enable = false;
		pr_info("policy[%d] disables boost it is %lu seconds after boot up\n",
			 policy->cpu, SPRD_CPUFREQ_BOOST_DURATION / HZ);
	}

	if (cluster->boost_enable) {
		if (policy->max >= policy->cpuinfo.max_freq ||
		    policy->min == policy->max)
			return ON_BOOST;
		cluster->boost_enable = false;
		pr_info("policy[%d] disables boost due to policy max(%d<%d)\n",
			policy->cpu, policy->max, policy->cpuinfo.max_freq);
	}

	return OUT_BOOST;
}

static int sprd_nvmem_info_read(struct device_node *node, const char *name, u32 *value)
{
	struct nvmem_cell *cell;
	void *buf;
	size_t len = 0;
	int ret = 0;

	cell = of_nvmem_cell_get(node, name);
	if (IS_ERR(cell)) {
		ret = PTR_ERR(cell);
		if (ret == -EPROBE_DEFER)
			pr_warn("cell for cpufreq not ready, retry\n");
		else
			pr_err("failed to get cell for cpufreq\n");

		return ret;
	}

	buf = nvmem_cell_read(cell, &len);
	if (IS_ERR(buf)) {
		nvmem_cell_put(cell);
		return PTR_ERR(buf);
	}

	if (len > sizeof(u32))
		len = sizeof(u32);

	memcpy(value, buf, len);

	kfree(buf);
	buf = NULL;

	nvmem_cell_put(cell);

	return 0;
}

static int sprd_temp_list_init(struct list_head *head)
{
	struct temp_node *node;

	if (!list_empty_careful(head)) {
		pr_warn("temp list is also init\n");
		return 0;
	}

	/* add upper temp node */
	node = devm_kzalloc(dev, sizeof(*node), GFP_KERNEL);
	if (!node)
		return -ENOMEM;

	node->temp = DVFS_TEMP_UPPER_LIMIT;

	list_add(&node->list, head);

	/* add low temp node */
	node = devm_kzalloc(dev, sizeof(*node), GFP_KERNEL);
	if (!node)
		return -ENOMEM;

	node->temp = DVFS_TEMP_LOW_LIMIT;

	list_add(&node->list, head);

	return 0;
}

static int sprd_temp_list_add(struct list_head *head, int temp)
{
	struct temp_node *node, *pos;

	if (temp_check(temp) || list_empty_careful(head)) {
		pr_err("temp %d or list is error\n", temp);
		return -EINVAL;
	}

	list_for_each_entry(pos, head, list) {
		if (temp == pos->temp)
			return 0;
		if (temp < pos->temp)
			break;
	}

	node = devm_kzalloc(dev, sizeof(*node), GFP_KERNEL);
	if (!node)
		return -ENOMEM;

	node->temp = temp;

	list_add_tail(&node->list, &pos->list);

	return 0;
}

static struct temp_node *sprd_temp_list_find(struct list_head *head, int temp)
{
	struct temp_node *pos, *next;

	if (temp_check(temp)) {
		pr_err("temp %d is out of range\n", temp);
		return NULL;
	}

	list_for_each_entry(pos, head, list) {
		next = list_entry(pos->list.next, typeof(*pos), list);
		if ((temp >= pos->temp) && (temp < next->temp))
			break;
	}

	return pos;
}

static u32 sprd_cpufreq_get_debug_flag(void)
{
	struct device_node *cmdline_node;
	const char *cmd_line, *dvfs_set;
	u32 value = 0;
	int ret;

	cmdline_node = of_find_node_by_path("/chosen");
	ret = of_property_read_string(cmdline_node, "bootargs", &cmd_line);

	if (ret) {
		pr_err("Fail to find cmdline bootargs property\n");
		return 0;
	}

	dvfs_set = strstr(cmd_line, "sprdboot.dvfs_set=0x");
	if (!dvfs_set) {
		pr_info("no property sprdboot.dvfs_set found\n");
		return 0;
	}

	sscanf(dvfs_set, "sprdboot.dvfs_set=0x%x", &value);

	return value;
}

static void sprd_cluster_get_supply_mode(char *dcdc_supply)
{
	struct device_node *cmdline_node;
	const char *cmd_line, *dcdc_type, *ver_str = "-v2";
	int value = -1, ret;

	cmdline_node = of_find_node_by_path("/chosen");
	ret = of_property_read_string(cmdline_node, "bootargs", &cmd_line);

	if (ret) {
		pr_err("Fail to find cmdline bootargs property\n");
		return;
	}

	dcdc_type = strstr(cmd_line, "power.from.extern=");
	if (!dcdc_type) {
		pr_info("no property power.from.extern found\n");
		return;
	}

	sscanf(dcdc_type, "power.from.extern=%d", &value);
	if (value)
		return;

	strcat(dcdc_supply, ver_str);
}

static int sprd_policy_table_update(struct cpufreq_policy *policy, struct temp_node *node)
{
	struct cpufreq_frequency_table *new_table __maybe_unused;
	struct cluster_info *cluster;
	struct device *cpu;
	u64 freq, vol;
	int i, ret;

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster || !cluster->table_update || !cluster->pair_get) {
		pr_err("get cpu %u cluster info error\n", policy->cpu);
		return -EINVAL;
	}

	cpu = get_cpu_device(cluster->cpu);
	if (!cpu) {
		pr_err("get cpu %u dev error\n", policy->cpu);
		return -EINVAL;
	}

	pr_info("update cluster %u temp %d dvfs table\n", cluster->id, node->temp);

	ret = cluster->table_update(cluster->id, node->temp, &cluster->table_entry_num);
	if (ret) {
		pr_err("update cluster %u temp %d table error\n", cluster->id, node->temp);
		return ret;
	}

	if (!cluster->table_entry_num || cluster->table_entry_num > 64)
		return -EINVAL;
	pr_debug("cluster %u dvfs table entry num is %u\n", cluster->id, cluster->table_entry_num);

	for (i = 0; i < cluster->table_entry_num; ++i) {
		ret = cluster->pair_get(cluster->id, i, &freq, &vol);
		if (ret) {
			pr_err("get cluster %u index %u pair error\n", cluster->id, i);
			return ret;
		}

		if (!freq || freq > UINT_MAX * 1000ULL || !vol || vol > UINT_MAX)
			return -EINVAL;
		pr_debug("add %lluHz/%lluuV to opp\n", freq, vol);

		if (policy->freq_table)
			dev_pm_opp_remove(cpu, freq);

		ret = dev_pm_opp_add(cpu, freq, vol);
		if (ret) {
			pr_err("add %lluHz/%lluuV pair to opp error(%d)\n", freq, vol, ret);
			return ret;
		}
	}

	if (node->temp_table)
		policy->freq_table = node->temp_table;
	else {
		ret = dev_pm_opp_init_cpufreq_table(cpu, &new_table);
		if (ret) {
			pr_err("init cluster %u freq table error(%d)\n", cluster->id, ret);
			return ret;
		}

		policy->freq_table = new_table;
		node->temp_table = new_table;
	}

	policy->suspend_freq = policy->freq_table[0].frequency;

	return 0;
}

static void sprd_cpufreq_temp_work_func(struct work_struct *work)
{
	int temp = 0, ret;
	unsigned int freq, cpu;
	struct cpumask cluster_online_mask;
	struct delayed_work *dwork = to_delayed_work(work);
	struct cluster_info *cluster =
		container_of(dwork, struct cluster_info, temp_work);

	if (!cluster) {
		pr_err("get temp work cluster info error\n");
		return;
	}

	if (IS_ERR_OR_NULL(cluster->cpu_tz)) {
		cluster->cpu_tz = thermal_zone_get_zone_by_name(cluster->tz_name);
		if (IS_ERR_OR_NULL(cluster->cpu_tz)) {
			pr_warn("failed to get cluster %u thmzone\n", cluster->id);
			queue_delayed_work(system_highpri_wq, &cluster->temp_work,
					   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));
			return;
		}

		pr_info("get cluster %u thmzone successfully\n", cluster->id);
	}

	ret = thermal_zone_get_temp(cluster->cpu_tz, &temp);
	if (ret) {
		pr_warn("failed to get the cluster %u temp of cpu thmzone\n", cluster->id);
		queue_delayed_work(system_highpri_wq, &cluster->temp_work,
				   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));
		return;
	}

	cpumask_and(&cluster_online_mask, &cluster->cpus, cpu_online_mask);
	cpu = cpumask_first(&cluster_online_mask);

	freq = cpu < nr_cpu_ids ? sprd_cpufreq_update_opp(cpu, temp) : 0;
	if (freq)
		pr_info("cluster[%u] update max freq[%u] by temp[%d]\n",
			cluster->id, freq, temp);

	queue_delayed_work(system_highpri_wq, &cluster->temp_work,
			   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));
}

/* sprd_cpufreq_driver interface */
static int sprd_cpufreq_init(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster;
	u64 freq = 0;
	int ret;

	cluster = pclusters + sprd_cluster_info(policy->cpu);
	if (!cluster || !cluster->freq_get || !cluster->dvfs_enable) {
		pr_err("get cpu %u cluster info error\n", policy->cpu);
		return -EINVAL;
	}

	mutex_lock(&cluster->mutex);

	/* CPUs in the same cluster share same clock and power domain */
	ret = 0;
	{
		int cpu;
		for_each_possible_cpu(cpu)
			if (sprd_cluster_info(cpu) == cluster->id)
				cpumask_set_cpu(cpu, policy->cpus);
	}
	if (ret < 0) {
		pr_err("cpufreq cluster cpumask error");
		goto unlock_ret;
	}
	cpumask_copy(&cluster->cpus, policy->cpus);

	/* init other cpu policy link in same cluster */
	policy->dvfs_possible_from_any_cpu = true;

	policy->transition_delay_us = cluster->transition_delay;
	policy->driver_data = cluster;

	/* init dvfs table use current temp */
	ret = sprd_policy_table_update(policy, cluster->temp_currt_node);
	if (ret) {
		pr_err("update cluster %u table error(%d)\n", cluster->id, ret);
		goto unlock_ret;
	}

	/* get current freq for policy */
	ret = cluster->freq_get(cluster->id, &freq);
	if (ret) {
		pr_err("get cluster %u current freq error\n", cluster->id);
		goto unlock_ret;
	}

	do_div(freq, 1000); /* from Hz to KHz */
	policy->cur = (u32)freq;

	/* enable dvfs phy */
	ret = cluster->dvfs_enable(cluster->id);
	if (ret) {
		pr_err("enable cluster %u dvfs error\n", cluster->id);
		goto unlock_ret;
	}

	/* init debugfs interface to debug dvfs */
	ret = sprd_debug_cluster_init(policy);
	if (ret) {
		pr_err("init cluster %u debug error(%d)\n", cluster->id, ret);
		goto unlock_ret;
	}

	if (cluster->temp_enable) {
		ret = freq_qos_add_request(&policy->constraints,
					   &cluster->max_req, FREQ_QOS_MAX,
					   FREQ_QOS_MAX_DEFAULT_VALUE);
		if (ret < 0) {
			pr_err("add cluster %u freq qos error(%d)\n", cluster->id, ret);
			goto unlock_ret;
		}

		queue_delayed_work(system_highpri_wq, &cluster->temp_work,
				   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));
	}

	mutex_unlock(&cluster->mutex);

	return 0;

unlock_ret:
	mutex_unlock(&cluster->mutex);

	return ret;
}

static void sprd_cpufreq_exit(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster;
	struct device *cpu;
	int ret;

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster) {
		pr_err("policy is not init\n");
		return;
	}

	cpu = get_cpu_device(policy->cpu);
	if (!cpu) {
		pr_err("get cpu %u device error\n", policy->cpu);
		return;
	}

	if (cluster->temp_enable) {
		cancel_delayed_work_sync(&cluster->temp_work);
		freq_qos_remove_request(&cluster->max_req);
	}

	mutex_lock(&cluster->mutex);
	{
		struct temp_node *node;
		list_for_each_entry(node, &cluster->temp_list_head, list)
			if (node->temp_table)
				dev_pm_opp_free_cpufreq_table(cpu, &node->temp_table);
	}
	policy->freq_table = NULL;
	dev_pm_opp_remove_all_dynamic(cpu);

	ret = sprd_debug_cluster_exit(policy);
	if (ret)
		pr_warn("cluster %u debug exit error\n", cluster->id);

	policy->driver_data = NULL;

	mutex_unlock(&cluster->mutex);

	return;
}

static int sprd_cpufreq_table_verify(struct cpufreq_policy_data *policy_data)
{
	return cpufreq_generic_frequency_table_verify(policy_data);
}

static int sprd_cpufreq_set_target_index(struct cpufreq_policy *policy, u32 index)
{
	struct cluster_info *cluster;
	unsigned int freq;
	int ret;

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster || !cluster->freq_set) {
		pr_err("policy is not init\n");
		return -EINVAL;
	}

	if (cluster->boost_enable) {
		ret = sprd_cpufreq_boost_judge(policy);
		if (ret == ON_BOOST)
			return 0;
	}

	mutex_lock(&cluster->mutex);

	if (index >= cluster->table_entry_num) {
		pr_err("cluster %u index %u is error\n", cluster->id, index);
		mutex_unlock(&cluster->mutex);
		return -EINVAL;
	}

	ret = cluster->freq_set(cluster->id, index);
	if (ret) {
		pr_err("set cluster %u index %u error(%d)\n", cluster->id, index, ret);
		mutex_unlock(&cluster->mutex);
		return ret;
	}

	freq = policy->freq_table[index].frequency;

	mutex_unlock(&cluster->mutex);

	return 0;
}

static u32 sprd_cpufreq_get(u32 cpu)
{
	struct cluster_info *cluster;
	u64 freq;
	int ret;

	cluster = pclusters + sprd_cluster_info(cpu);
	if (!cluster || !cluster->freq_get) {
		pr_err("get cpu %u cluster info error\n", cpu);
		return 0;
	}

	mutex_lock(&cluster->mutex);

	ret = cluster->freq_get(cluster->id, &freq);
	if (ret) {
		pr_err("get cluster %u current freq error\n", cluster->id);
		mutex_unlock(&cluster->mutex);
		return 0;
	}

	mutex_unlock(&cluster->mutex);

	do_div(freq, 1000); /* from Hz to KHz */

	return (u32)freq;
}

static int sprd_cpufreq_suspend(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster = policy->driver_data;

	if (cluster->temp_enable)
		cancel_delayed_work_sync(&cluster->temp_work);

	if (!strcmp(policy->governor->name, "userspace")) {
		pr_info("do nothing for governor-%s\n", policy->governor->name);
		return 0;
	}

	if (cluster->boost_enable) {
		cluster->boost_enable = false;
		sprd_cpufreq_set_target_index(policy, 0);
	}

	return cpufreq_generic_suspend(policy);
}

static int sprd_cpufreq_resume(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster = policy->driver_data;

	if (cluster->temp_enable)
		queue_delayed_work(system_highpri_wq, &cluster->temp_work,
				   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));

	if (!strcmp(policy->governor->name, "userspace")) {
		pr_info("do nothing for governor-%s\n", policy->governor->name);
		return 0;
	}

	return 0;
}

static int sprd_cpufreq_online(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster;

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster) {
		pr_err("policy is not init\n");
		return -EINVAL;
	}

	if (cluster->temp_enable)
		queue_delayed_work(system_highpri_wq, &cluster->temp_work,
				   msecs_to_jiffies(DVFS_TEMP_UPDATE_MS));

	return 0;
}

static int sprd_cpufreq_offline(struct cpufreq_policy *policy)
{
	struct cluster_info *cluster;

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster) {
		pr_err("policy is not init\n");
		return -EINVAL;
	}

	if (cluster->temp_enable)
		cancel_delayed_work_sync(&cluster->temp_work);

	return 0;
}

static ssize_t show_scaling_voltage_table(struct cpufreq_policy *policy, char *buf)
{
	struct cluster_info *cluster = policy->driver_data;
	u64 freq, volt;
	int i, ret, len = 0;
	mutex_lock(&cluster->mutex);
	for (i = 0; i < cluster->table_entry_num; i++) {
		ret = cluster->pair_get(cluster->id, i, &freq, &volt);
		if (ret) { len = ret; break; }
		len += sysfs_emit_at(buf, len, "%llu %llu\n", freq / 1000, volt);
	}
	mutex_unlock(&cluster->mutex);
	return len;
}
cpufreq_freq_attr_ro(scaling_voltage_table);
static ssize_t show_scaling_voltage_offset(struct cpufreq_policy *policy, char *buf)
{
	struct cluster_info *cluster = policy->driver_data;
	return sysfs_emit(buf, "%d\n", cluster->id < 3 ? voltage_offset_uv[cluster->id] : 0);
}
static ssize_t show_scaling_voltage_domain(struct cpufreq_policy *policy, char *buf)
{
	struct cluster_info *cluster = policy->driver_data;
	return sysfs_emit(buf, "%u\n", cluster->id);
}
cpufreq_freq_attr_ro(scaling_voltage_offset);
cpufreq_freq_attr_ro(scaling_voltage_domain);
/* Keep userspace requests distinct from effective thermal/QoS limits. */
static ssize_t show_scaling_requested_min_freq(struct cpufreq_policy *policy, char *buf)
{
	return sysfs_emit(buf, "%u\n", clamp_t(unsigned int,
		READ_ONCE(policy->min_freq_req->pnode.prio),
		policy->cpuinfo.min_freq, policy->cpuinfo.max_freq));
}
static ssize_t show_scaling_requested_max_freq(struct cpufreq_policy *policy, char *buf)
{
	return sysfs_emit(buf, "%u\n", clamp_t(unsigned int,
		READ_ONCE(policy->max_freq_req->pnode.prio),
		policy->cpuinfo.min_freq, policy->cpuinfo.max_freq));
}
cpufreq_freq_attr_ro(scaling_requested_min_freq);
cpufreq_freq_attr_ro(scaling_requested_max_freq);
static struct freq_attr *sprd_cpufreq_attr[] = {
	&scaling_voltage_table,
	&scaling_voltage_offset,
	&scaling_voltage_domain,
	&scaling_requested_min_freq,
	&scaling_requested_max_freq,
	NULL,
};

static struct cpufreq_driver sprd_cpufreq_driver = {
	.name = "sprd-cpufreq-v2",
	.flags = CPUFREQ_NEED_INITIAL_FREQ_CHECK |
		 CPUFREQ_HAVE_GOVERNOR_PER_POLICY |
		 CPUFREQ_IS_COOLING_DEV,
	.init = sprd_cpufreq_init,
	.exit = sprd_cpufreq_exit,
	.verify = sprd_cpufreq_table_verify,
	.target_index = sprd_cpufreq_set_target_index,
	.register_em = cpufreq_register_em_with_opp,
	.get = sprd_cpufreq_get,
	.suspend = sprd_cpufreq_suspend,
	.resume = sprd_cpufreq_resume,
	.online = sprd_cpufreq_online,
	.offline = sprd_cpufreq_offline,
	.attr = sprd_cpufreq_attr,
};

/* init inerface */
static int sprd_cluster_temp_init(struct cluster_info *cluster)
{
	const char *name = "sprd,temp-threshold";
	struct temp_node *node;
	struct property *prop;
	u32 num, val;
	int i, ret;

	INIT_LIST_HEAD(&cluster->temp_list_head);

	ret = sprd_temp_list_init(&cluster->temp_list_head);
	if (ret) {
		pr_err("init cluster %u temp limit error(%d)\n", cluster->id, ret);
		return ret;
	}

	prop = of_find_property(cluster->node, name, &num);
	if (!prop || !num) {
		pr_warn("find cluster %u temp property error\n", cluster->id);
		cluster->temp_enable = false;
		goto temp_node_init;
	}

	cluster->temp_enable = true;
	INIT_DELAYED_WORK(&cluster->temp_work, sprd_cpufreq_temp_work_func);

	if (of_property_read_string(cluster->node, "sprd,thmzone-names", &cluster->tz_name)) {
		pr_err("get cluster %u thmzone name error\n", cluster->id);
		return -EINVAL;
	}

	for (i = 0; i < num / sizeof(u32); i++) {
		ret = of_property_read_u32_index(cluster->node, name, i, &val);
		if (ret) {
			pr_err("get cluster %u temp error\n", cluster->id);
			return ret;
		}

		ret = sprd_temp_list_add(&cluster->temp_list_head, (int)val);
		if (ret) {
			pr_err("add cluster %u temp error(%d)\n", cluster->id, ret);
			return ret;
		}
	}

temp_node_init:
	node = sprd_temp_list_find(&cluster->temp_list_head, DVFS_TEMP_DEFAULT);
	if (!node) {
		pr_err("init cluster %u temp(%d) node error\n", cluster->id, DVFS_TEMP_DEFAULT);
		return -EINVAL;
	}

	cluster->temp_level_node = node;
	cluster->temp_currt_node = node;
	cluster->best_temp = node->temp;
	cluster->temp_tick = 0U;

	return 0;
}

static int sprd_cluster_props_init(struct cluster_info *cluster)
{
	int (*ops)(u32 id, u32 val);
	struct cluster_prop *p;
	struct device_node *hwf;
	int i, ret;
	const char *dvfs_bin;
	char dcdc_supply[32] = "sprd,pmic-type";
	struct cluster_prop props[] = {
		{
			.name = "sprd,voltage-step",
			.value = &cluster->voltage_step,
			.ops = (void **)&cluster->step_set,
		}, {
			.name = "sprd,voltage-margin",
			.value = &cluster->voltage_margin,
			.ops = (void **)&cluster->margin_set,
		}, {
			.name = "sprd,transition-delay",
			.value = &cluster->transition_delay,
			.ops = NULL,
		}
	};

	for (i = 0; i < ARRAY_SIZE(props); ++i) {
		p = props + i;
		ops = p->ops ? *p->ops : NULL;

		ret = of_property_read_u32(cluster->node, p->name, p->value);
		if (ret) {
			pr_warn("get cluster %u '%s' value error\n", cluster->id, p->name);
			*p->value = 0U;
			continue;
		}

		ret = ops ? ops(cluster->id, *p->value) : 0;
		if (ret) {
			pr_err("set cluster %u '%s' value error\n", cluster->id, p->name);
			return -EINVAL;
		}
	}

	if (of_property_read_bool(cluster->node, "sprd,multi-supply"))
		sprd_cluster_get_supply_mode(dcdc_supply);

	pr_info("cluster %u dcdc supply[%s]\n", cluster->id, dcdc_supply);

	ret = of_property_read_u32(cluster->node, dcdc_supply, &cluster->pmic_type);
	if (!ret) {
		ret = cluster->pmic_set(cluster->id, cluster->pmic_type);
		if (ret) {
			pr_err("set cluster %u 'pmic-type' value error\n", cluster->id);
			return -EINVAL;
		}
	}

	if (cluster->id == 0) {
		ret = cluster->dvfs_debug_init();
		if (ret) {
			pr_err("dvfs debug init error\n");
			return ret;
		}
	}

	ret = of_property_read_string(cluster->node, "nvmem-cell-names", &dvfs_bin);
	if (ret == -EINVAL) { /* No definition is allowed */
		pr_warn("Warning: no 'dvfs_bin' appointed\n");
		cluster->bin = 0U;
	} else {
		ret = sprd_nvmem_info_read(cluster->node, dvfs_bin, &cluster->bin);
		if (ret) {
			pr_err("read dvfs bin value error(%d)\n", ret);
			return ret;
		}

		ret = cluster->bin_set(cluster->id, cluster->bin);
		if (ret) {
			pr_err("set cluster %u 'binning' value error\n", cluster->id);
			return ret;
		}
	}

	if (of_property_read_bool(cluster->node, "sprd,multi-version")) {
		hwf = of_find_node_by_path("/hwfeature/auto");
		if (IS_ERR_OR_NULL(hwf)) {
			pr_err("no hwfeature/auto node found\n");
			return -EINVAL;
		}

		/* The ABI consumes one raw word. Some factory DTs store a short
		 * version string here; pad it rather than reading past the property.
		 */
		{
			int length;
			const void *version = of_get_property(hwf, "efuse", &length);
			if (!version || length <= 0) {
				of_node_put(hwf);
				return -EINVAL;
			}
			memcpy(&cluster->version, version,
			       min_t(size_t, length, sizeof(cluster->version)));
		}
		of_node_put(hwf);
		ret = cluster->version_set(cluster->id, &cluster->version);
		if (ret) {
			pr_err("set cluster %u 'version' value error\n", cluster->id);
			return ret;
		}
	}

	/* Honor governor and thermal requests immediately, without a boot boost. */
	cluster->boost_enable = false;

	return 0;
}

static int sprd_cluster_ops_init(struct cluster_info *cluster)
{
	struct sprd_sip_svc_dvfs_ops *ops;
	struct sprd_sip_svc_handle *sip;

	sip = sprd_sip_svc_get_handle();
	if (!sip) {
		pr_err("get sip error\n");
		return -EINVAL;
	}

	ops = &sip->dvfs_ops;

	cluster->dvfs_enable = ops->dvfs_enable;
	cluster->table_update = ops->table_update;
	cluster->step_set = ops->step_set;
	cluster->margin_set = ops->margin_set;
	cluster->freq_set = ops->freq_set;
	cluster->freq_get = ops->freq_get;
	cluster->pair_get = ops->pair_get;
	cluster->pmic_set = ops->pmic_set;
	cluster->bin_set = ops->bin_set;
	cluster->version_set = ops->version_set;
	cluster->dvfs_init = ops->dvfs_init;
	cluster->dvfs_debug_init = ops->dvfs_debug_init;

	return 0;
}

static struct device_node *sprd_cluster_node_init(u32 cpu_idx)
{
	struct device *cpu_dev;

	cpu_dev = get_cpu_device(cpu_idx);
	if (!cpu_dev)
		return NULL;

	return of_parse_phandle(cpu_dev->of_node, "sprd,freq-domain", 0);
}

static int sprd_cluster_info_init(struct cluster_info *clusters)
{
	struct cluster_info *cluster;
	unsigned int cpu;
	int ret;

	for_each_possible_cpu(cpu) {
		cluster = clusters + sprd_cluster_info(cpu);
		if (cluster->node) {
			pr_debug("cluster %u info is also init\n", cluster->id);
			continue;
		}

		cluster->node = sprd_cluster_node_init(cpu);
		if (!cluster->node) {
			pr_err("init cluster %u node error\n", cluster->id);
			return -EINVAL;
		}

		cluster->id = (u32)sprd_cluster_info(cpu);
		cluster->cpu = cpu;

		mutex_init(&cluster->mutex);

		ret = sprd_cluster_ops_init(cluster);
		if (ret) {
			pr_err("init cluster %u ops error(%d)\n", cluster->id, ret);
			return ret;
		}

		ret = sprd_cluster_props_init(cluster);
		if (ret) {
			pr_err("init cluster %u props error(%d)\n", cluster->id, ret);
			return ret;
		}

		ret = sprd_cluster_temp_init(cluster);
		if (ret) {
			pr_err("init cluster %u temp error(%d)\n", cluster->id, ret);
			return ret;
		}
	}

	return 0;
}

static int sprd_cpufreq_driver_probe(struct platform_device *pdev)
{
	int ret, count;
	u32 flag;

	flag = sprd_cpufreq_get_debug_flag();
	ret = sprd_voltage_flag(&flag);
	if (ret)
		return ret;
	if (firmware_initialized)
		return -EBUSY;
	if ((flag & 0xFF) == SPRD_DVFS_DEBUG_MAGIC) {
		pr_info("disable apcpu dvfs for debug!\n");
		return 0;
	}

	boot_done_timestamp = jiffies + SPRD_CPUFREQ_BOOST_DURATION;

	dev = &pdev->dev;

	pr_debug("probe sprd cpufreq v2 driver\n");

	count = sprd_cluster_num();
	if (count <= 0)
		return count ? count : -EINVAL;
	pclusters = devm_kcalloc(dev, count, sizeof(*pclusters), GFP_KERNEL);
	if (!pclusters)
		return -ENOMEM;

	ret = sprd_cluster_info_init(pclusters);
	if (ret) {
		pr_err("init cluster info error(%d)\n", ret);
		return ret;
	}

	firmware_initialized = true;
	ret = pclusters->dvfs_init(flag);
	if (ret) {
		pr_err("init dvfs device error\n");
		return ret;
	}

	ret = sprd_debug_init(dev);
	if (ret) {
		pr_err("init dvfs debug error(%d)\n", ret);
		return ret;
	}

	ret = cpufreq_register_driver(&sprd_cpufreq_driver);
	if (ret)
		pr_err("register cpufreq driver error\n");
	else
		pr_info("register cpufreq driver success\n");

	return ret;
}

static void sprd_cpufreq_driver_remove(struct platform_device *pdev)
{
	cpufreq_unregister_driver(&sprd_cpufreq_driver);
}

/**
 * sprd_cpufreq_update_opp() - returns the max freq of a cpu and update dvfs
 * table by temp_now
 *
 * @cpu: which cpu you want to update dvfs table
 * @now_temp: current temperature on this cpu, mini-degree.
 *
 * Return:
 * 1.cluster is not working, then return 0
 * 2.succeed to update dvfs table then return max freq(KHZ) of this cluster
 */
unsigned int sprd_cpufreq_update_opp(unsigned int cpu, int now_temp)
{
	struct cpufreq_policy *policy;
	struct cluster_info *cluster;
	int temp = now_temp / 1000;
	struct temp_node *node;
	u64 freq;
	int ret;

	policy = cpufreq_cpu_get(cpu);
	if (!policy) {
		pr_err("get cpu %u policy error\n", cpu);
		return 0;
	}

	cluster = (struct cluster_info *)policy->driver_data;
	if (!cluster || !cluster->pair_get) {
		pr_err("cpu %u cluster info error\n", cpu);
		cpufreq_cpu_put(policy);
		return 0;
	}

	if (!down_write_trylock(&policy->rwsem)) {
		cpufreq_cpu_put(policy);
		return 0;
	}
	mutex_lock(&cluster->mutex);

	node = sprd_temp_list_find(&cluster->temp_list_head, temp);

	if (!node) {
		cluster->temp_level_node = cluster->temp_currt_node;
		cluster->temp_tick = 0U;
		goto ret_error;
	}

	/* immediate response to away from the best_temp */
	if (abs(node->temp - cluster->best_temp)
	    - abs(cluster->temp_currt_node->temp - cluster->best_temp) > 0) {
		cluster->temp_level_node = node;
		cluster->temp_tick = DVFS_TEMP_MAX_TICKS;
	} else if (node != cluster->temp_level_node) {
		cluster->temp_level_node = node;
		cluster->temp_tick = 0U;
		goto ret_error;
	}

	++cluster->temp_tick;
	if (cluster->temp_tick < DVFS_TEMP_MAX_TICKS)
		goto ret_error;

	cluster->temp_tick = 0U;

	if (cluster->temp_level_node == cluster->temp_currt_node)
		goto ret_error;

	pr_debug("update cluster %u table to %d(%d)\n", cluster->id, temp,
		 cluster->temp_level_node->temp);

	/* delay is required to ensure that the last process is completed */
	udelay(100);

	ret = sprd_policy_table_update(policy, cluster->temp_level_node);
	if (ret) {
		pr_err("update cluster %u table error(%d)\n", cluster->id, ret);
		goto ret_error;
	}

	cluster->temp_currt_node = cluster->temp_level_node;

	ret = cluster->pair_get(cluster->id, cluster->table_entry_num - 1, &freq, NULL);
	if (ret) {
		pr_err("get cluster %u max freq error\n", cluster->id);
		goto ret_error;
	}

	do_div(freq, 1000); /* from Hz to KHz */

	ret = freq_qos_update_request(&cluster->max_req, freq);
	if (ret < 0) {
		pr_err("cluster %u qos update max freq(%llu) error\n", cluster->id, freq);
		goto ret_error;
	}

	udelay(100);

	mutex_unlock(&cluster->mutex);
	up_write(&policy->rwsem);
	cpufreq_cpu_put(policy);

	return (unsigned int)freq;

ret_error:
	mutex_unlock(&cluster->mutex);
	up_write(&policy->rwsem);
	cpufreq_cpu_put(policy);

	return 0;
}

static const struct of_device_id sprd_cpufreq_of_match[] = {
	{
		.compatible = "sprd,cpufreq-v2",
	},
	{
		/* Sentinel */
	},
};

static struct platform_driver sprd_cpufreq_platform_driver = {
	.driver = {
		.name = "sprd-cpufreq-v2",
		.of_match_table = sprd_cpufreq_of_match,
		/* Rebinding would apply offsets twice to firmware-owned tables. */
		.suppress_bind_attrs = true,
	},
	.probe = sprd_cpufreq_driver_probe,
	.remove = sprd_cpufreq_driver_remove,
};

static int __init sprd_cpufreq_platform_driver_register(void)
{
	return platform_driver_register(&sprd_cpufreq_platform_driver);
}

device_initcall(sprd_cpufreq_platform_driver_register);

MODULE_DESCRIPTION("sprd cpufreq v2 driver");
MODULE_LICENSE("GPL v2");
