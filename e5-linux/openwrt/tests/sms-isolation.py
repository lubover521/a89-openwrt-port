#!/usr/bin/env python3
"""Compile and execute the shipped SMS context callbacks with a fake AT owner."""
from pathlib import Path
import subprocess,tempfile,sys

source=Path(sys.argv[1])
text=(source/'plugins/unisoc/mm-broadband-modem-unisoc.c').read_text()
a=text.index('typedef struct {\n    gchar *response;\n    GError *error;\n} ScopedSmsCommand;')
b=text.index('\ntypedef struct {\n    MMIfacePortAt *port;',a)
functions=text[a:b]
events=text[text.index('static void\nmessaging_events_ready'):a]
assert 'messaging_events_setup' in text and 'G_FILE_TEST_IS_EXECUTABLE' in text
header=r'''
#include <gio/gio.h>
#include <string.h>
typedef GObject MMBaseModem;
typedef GObject MMIfaceModemMessaging;
typedef GObject MMPortSerialAt;
typedef struct {
    gboolean (*setup_unsolicited_events_finish)(MMIfaceModemMessaging *,GAsyncResult *,GError **);
    void (*setup_unsolicited_events)(MMIfaceModemMessaging *,GAsyncReadyCallback,gpointer);
} MessagingParent;
static MessagingParent *iface_modem_messaging_parent;
static gboolean receiver_available,events_failure;
static guint suppressed;
#define MM_BASE_MODEM(x) (x)
#define mm_obj_info(...) ((void)0)
static gboolean receiver_exists(const gchar *p,GFileTest flag){g_assert_cmpstr(p,==,"/usr/libexec/e5-sms-receive");return receiver_available;}
#define g_file_test receiver_exists
static MMPortSerialAt *mm_base_modem_peek_port_primary(MMBaseModem *s){return s;}
static MMPortSerialAt *mm_base_modem_peek_port_secondary(MMBaseModem *s){return s;}
static GRegex *mm_3gpp_cmti_regex_get(void){return g_regex_new("CMTI",0,0,NULL);}
static void mm_port_serial_at_add_unsolicited_msg_handler(MMPortSerialAt *p,GRegex *r,gpointer cb,gpointer data,gpointer destroy){g_assert_null(cb);suppressed++;}
static gboolean events_finish(MMIfaceModemMessaging *s,GAsyncResult *r,GError **e){
    if(events_failure){g_set_error_literal(e,G_IO_ERROR,G_IO_ERROR_FAILED,"setup failed");return FALSE;}return TRUE;
}
static GTask *events_task;
static void events_setup(MMIfaceModemMessaging *s,GAsyncReadyCallback cb,gpointer task){events_task=g_object_ref(task);cb(s,NULL,task);}
static guint selected, own, restores;
static gboolean restore_error;
typedef struct {const gchar *reply; gboolean error;} Result;
static guint port_card(void) {return own;}
#define mm_obj_warn(...) ((void)0)
static const gchar *mm_base_modem_at_command_finish(MMBaseModem *s,GAsyncResult *r,GError **error) {
    Result *result=(Result *)r;
    if(result->error){g_set_error_literal(error,G_IO_ERROR,G_IO_ERROR_FAILED,"SIM2 CMS failure");return NULL;}
    return result->reply;
}
static void mm_base_modem_at_command(MMBaseModem *s,const gchar *cmd,guint timeout,gboolean cached,GAsyncReadyCallback cb,gpointer task) {
    guint slot=99;g_assert_cmpint(sscanf(cmd,"+SPACTCARD=%u",&slot),==,1);
    g_assert_cmpuint(slot,==,own);g_assert_cmpuint(timeout,==,5);g_assert_false(cached);
    selected=slot;restores++;Result r={"",restore_error};cb(G_OBJECT(s),(GAsyncResult *)&r,task);
}
'''
body=r'''
static void test(guint slot,gboolean original_error,gboolean failure) {
    own=slot;selected=1-slot;restores=0;restore_error=failure;
    GObject *modem=g_object_new(G_TYPE_OBJECT,NULL);
    GTask *task=g_task_new(modem,NULL,NULL,NULL);g_object_ref(task);
    ScopedSmsCommand *ctx=g_new0(ScopedSmsCommand,1);
    g_task_set_task_data(task,ctx,(GDestroyNotify)scoped_sms_free);
    Result result={"+CMGL: 1,0,,20",original_error};
    scoped_sms_ready(modem,(GAsyncResult *)&result,task);
    while(!g_task_get_completed(task))g_main_context_iteration(NULL,TRUE);
    GError *error=NULL;gchar *reply=g_task_propagate_pointer(task,&error);
    g_assert_cmpuint(selected,==,own);g_assert_cmpuint(restores,==,1);
    if(original_error||failure){g_assert_nonnull(error);g_assert_null(reply);g_clear_error(&error);}
    else {g_assert_null(error);g_assert_cmpstr(reply,==,"+CMGL: 1,0,,20");}
    g_object_unref(task);g_object_unref(modem);
}
int main(void){
    g_assert_true(scoped_sms_command("+SPACTCARD=1;+CMGL=4"));
    g_assert_true(scoped_sms_command("+SPACTCARD=0;+CNMI=2,1,0,0,0"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGS=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGW=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0;+CMGS=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=0;+CSCS=\"GSM\";+CMGW=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CNMI?;+CMGF=0; AT+CMGS=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0;at+cmgw=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0;+CMGC=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0;+UNKNOWN=1"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0;+CPMS=\"SM\""));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGFAKE=0"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CSCS=\"GSM"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0\rAT+CMGS=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CMGF=0\nAT+CMGW=20"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;"));
    g_assert_true(scoped_sms_command("+SPACTCARD=1;+CMGF=0;+CMGL=4"));
    g_assert_true(scoped_sms_command("+SPACTCARD=0; AT+CPMS? ; +CNMI?;"));
    g_assert_true(scoped_sms_command("+SPACTCARD=1;+CSCS=\"text;+CMGS=20\";+CMGF=0"));
    g_assert_true(scoped_sms_command("+SPACTCARD=1;+CSCS=\"text;+CMGW=20\";+CMGF=0"));
    g_assert_false(scoped_sms_command("+SPACTCARD=2;+CMGL=4"));
    g_assert_false(scoped_sms_command("+SPACTCARD=1;+CFUN=4"));
    for(guint slot=0;slot<2;slot++){test(slot,FALSE,FALSE);test(slot,TRUE,FALSE);test(slot,FALSE,TRUE);}
    static MessagingParent parent={events_finish,events_setup};iface_modem_messaging_parent=&parent;
    for(guint mode=0;mode<3;mode++) {
        receiver_available=(mode!=0);events_failure=(mode==2);suppressed=0;
        GObject *modem=g_object_new(G_TYPE_OBJECT,NULL);
        messaging_events_setup(modem,NULL,NULL);GTask *task=events_task;
        while(!g_task_get_completed(task))g_main_context_iteration(NULL,TRUE);
        GError *error=NULL;gboolean result=messaging_events_finish(modem,G_ASYNC_RESULT(task),&error);
        g_assert_cmpint(result,==,!events_failure);g_assert_cmpuint(suppressed,==,(mode==1?2:0));
        g_clear_error(&error);g_object_unref(task);g_object_unref(modem);
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'test.c').write_text('#include <stdio.h>\n'+header+events+functions+body)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','gio-2.0'],text=True).split()
    subprocess.run(['cc','-Wall','-Werror=implicit-function-declaration',str(p/'test.c'),'-o',str(p/'test'),*flags],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS: both slot orders, CMS failure, restore failure, no prompt splitting or RF/data mutation')
