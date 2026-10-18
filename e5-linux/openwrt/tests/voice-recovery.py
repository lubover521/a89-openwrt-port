#!/usr/bin/env python3
"""Run actual Unisoc snapshot/recovery functions with in-memory calls, no AT I/O."""
from pathlib import Path
import shlex, subprocess, sys, tempfile
root=Path(sys.argv[1])
base=(root/'mm-base-call.c').read_text()
plugin=(root/'plugins/unisoc/mm-broadband-modem-unisoc.c').read_text()
voice=(root/'mm-iface-modem-voice.c').read_text()
def extract(text,start):
    a=text.index(start);return text[a:text.index('\n}\n',a)+3]
callback=extract(plugin,'static void voice_query_ready (')
retry=extract(plugin,'static gboolean voice_retry_empty (')
recover=extract(voice,'static gboolean\nrecover_unisoc_outgoing_call (')
model=r'''
#include <glib.h>
#include <string.h>
typedef enum { MM_CALL_STATE_UNKNOWN,MM_CALL_STATE_DIALING,MM_CALL_STATE_RINGING_OUT,MM_CALL_STATE_RINGING_IN,MM_CALL_STATE_ACTIVE,MM_CALL_STATE_HELD,MM_CALL_STATE_WAITING,MM_CALL_STATE_TERMINATED } MMCallState;
enum { MM_CALL_DIRECTION_UNKNOWN,MM_CALL_DIRECTION_INCOMING,MM_CALL_DIRECTION_OUTGOING };
#define MM_CALL_STATE_REASON_UNKNOWN 0
#define MM_CORE_ERROR g_quark_from_static_string("fake")
#define MM_CORE_ERROR_FAILED 1
#define MM_MODEM_CHARSET_UCS2 1
#define mm_obj_info(...) ((void)0)
#define G_TASK(x) (x)
#define G_OBJECT(x) (x)
#define MM_GDBUS_CALL(x) (x)
typedef struct {guint index,sim_slot,direction;MMCallState state;gchar *number;} MMCallInfo;
typedef struct {guint slot,own;gint64 started_at;gboolean empty_retried;GList *calls;GError *error;} VoiceListContext;
typedef VoiceListContext GTask;
typedef struct {int unused;} MMBaseModem;
typedef struct {int unused;} GAsyncResult;
static guint advances,timers;static GSourceFunc scheduled;static gpointer scheduled_data;
static gboolean present[2],fail_read;static const gchar *reply;
static VoiceListContext *g_task_get_task_data(GTask *task){return task;}
static const gchar *mm_base_modem_at_command_finish(MMBaseModem*m,GAsyncResult*r,GError**e){
    if(fail_read)g_set_error_literal(e,MM_CORE_ERROR,1,"read failed");return reply;
}
static void mm_3gpp_parse_clcc_response(const gchar*s,MMBaseModem*m,GList**list,GError**error){
    if(s && strstr(s,"+CLCC:")){MMCallInfo*c=g_new0(MMCallInfo,1);c->index=1;c->direction=MM_CALL_DIRECTION_OUTGOING;c->state=MM_CALL_STATE_DIALING;*list=g_list_append(NULL,c);}
}
static gboolean has_live_on_slot(MMBaseModem*m,guint slot){return present[slot-1];}
static gchar *mm_modem_charset_str_to_utf8(const gchar*a,int b,int c,gboolean d,GError**e){return NULL;}
static guint fake_timeout(guint ms,GSourceFunc fn,gpointer data){g_assert_cmpuint(ms,==,250);timers++;scheduled=fn;scheduled_data=data;return 1;}
#define g_timeout_add fake_timeout
static void voice_query_next(GTask *task){advances++;}
typedef struct {guint slot,index;MMCallState state;guint direction;} MMBaseCall;
typedef struct {guint count;MMBaseCall*last;} MMCallList;
typedef struct {gboolean enabled,pending;gint64 ended,snapshot;} MMIfaceModemVoice;
static guint created,exports,audio;
static MMBaseCall* create_call(MMIfaceModemVoice*self,guint direction,const gchar*number){created++;MMBaseCall*c=g_new0(MMBaseCall,1);c->direction=direction;return c;}
static struct { MMBaseCall*(*create_call)(MMIfaceModemVoice*,guint,const gchar*); } iface={create_call};
#define MM_IFACE_MODEM_VOICE_GET_IFACE(x) (&iface)
static gpointer g_object_get_data(MMIfaceModemVoice*self,const gchar*key){if(!strcmp(key,"e5-voice-hangup-at"))return self->ended?&self->ended:NULL;
    if(!strcmp(key,"e5-voice-snapshot-start"))return self->snapshot?&self->snapshot:NULL;
    if(!strcmp(key,"e5-voice-hangup-pending"))return GINT_TO_POINTER(self->pending);
    g_assert_cmpstr(key,==,"e5-dual-sim-voice");return GINT_TO_POINTER(self->enabled);}
static void mm_gdbus_call_set_sim_slot(MMBaseCall*c,guint slot){c->slot=slot;}
static void mm_base_call_set_index(MMBaseCall*c,guint index){c->index=index;}
static void mm_base_call_change_state(MMBaseCall*c,MMCallState state,int reason){c->state=state;}
static void update_audio_settings_in_call(MMIfaceModemVoice*s,MMBaseCall*c){audio++;}
static void mm_base_call_export(MMBaseCall*c){exports++;}
static void mm_call_list_add_call(MMCallList*l,MMBaseCall*c){l->count++;l->last=c;}
static void g_object_unref(gpointer p){}
'''
tests=r'''
int main(void){
    MMBaseModem modem={0};VoiceListContext ctx={0};
    present[0]=TRUE;reply="";
    voice_query_ready(&modem,NULL,&ctx);
    g_assert_cmpuint(ctx.slot,==,0);g_assert_cmpuint(advances,==,0);g_assert_cmpuint(timers,==,1);g_assert_true(ctx.empty_retried);
    g_assert_false(scheduled(scheduled_data));g_assert_cmpuint(advances,==,1);
    reply="+CLCC: 1,0,2,0,0";voice_query_ready(&modem,NULL,&ctx);
    g_assert_cmpuint(ctx.slot,==,1);g_assert_cmpuint(g_list_length(ctx.calls),==,1);g_assert_null(ctx.error);g_assert_false(ctx.empty_retried);
    g_assert_cmpuint(((MMCallInfo*)ctx.calls->data)->sim_slot,==,1);
    g_list_free_full(ctx.calls,g_free);
    /* A genuinely ended call is published empty after exactly one confirmation. */
    ctx=(VoiceListContext){.slot=1};present[1]=TRUE;reply="";timers=advances=0;
    voice_query_ready(&modem,NULL,&ctx);g_assert_cmpuint(timers,==,1);g_assert_cmpuint(ctx.slot,==,1);
    scheduled(scheduled_data);voice_query_ready(&modem,NULL,&ctx);
    g_assert_cmpuint(ctx.slot,==,2);g_assert_cmpuint(timers,==,1);g_assert_null(ctx.calls);g_assert_null(ctx.error);
    /* A failed confirmation cannot publish a false empty list. */
    ctx=(VoiceListContext){0};reply="";voice_query_ready(&modem,NULL,&ctx);
    fail_read=TRUE;voice_query_ready(&modem,NULL,&ctx);g_assert_nonnull(ctx.error);g_clear_error(&ctx.error);fail_read=FALSE;
    /* Idle/absent slots never acquire an extra poll. */
    ctx=(VoiceListContext){0};present[0]=FALSE;timers=0;voice_query_ready(&modem,NULL,&ctx);
    g_assert_cmpuint(timers,==,0);g_assert_cmpuint(ctx.slot,==,1);
    /* Adopt each live outgoing state on its own slot/index; no start operation exists in this harness. */
    MMIfaceModemVoice self={TRUE};MMCallList list={0};MMCallInfo info={.index=3,.sim_slot=2,.direction=MM_CALL_DIRECTION_OUTGOING};
    MMCallState states[]={MM_CALL_STATE_DIALING,MM_CALL_STATE_RINGING_OUT,MM_CALL_STATE_ACTIVE,MM_CALL_STATE_HELD};
    for(guint i=0;i<G_N_ELEMENTS(states);i++){
        info.state=states[i];g_assert_true(recover_unisoc_outgoing_call(&self,&list,&info));
        g_assert_cmpuint(list.last->slot,==,2);g_assert_cmpuint(list.last->index,==,3);g_assert_cmpuint(list.last->state,==,states[i]);g_free(list.last);
    }
    g_assert_cmpuint(created,==,4);g_assert_cmpuint(exports,==,4);g_assert_cmpuint(audio,==,4);
    info.state=MM_CALL_STATE_TERMINATED;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    info.state=MM_CALL_STATE_ACTIVE;info.direction=MM_CALL_DIRECTION_INCOMING;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    info.direction=MM_CALL_DIRECTION_OUTGOING;info.sim_slot=0;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    info.sim_slot=2;info.index=0;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    info.index=3;self.enabled=FALSE;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));g_assert_cmpuint(created,==,4);
    self.enabled=TRUE; self.pending=TRUE;
    g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    self.pending=FALSE; self.ended=g_get_monotonic_time()-3*G_USEC_PER_SEC;
    self.snapshot=self.ended-1;
    g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    self.snapshot=0;g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    self.ended=g_get_monotonic_time();self.snapshot=self.ended+1;
    g_assert_false(recover_unisoc_outgoing_call(&self,&list,&info));
    self.ended-=3*G_USEC_PER_SEC;
    g_assert_true(recover_unisoc_outgoing_call(&self,&list,&info));g_free(list.last);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(model+retry+callback+recover+tests)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','glib-2.0'],text=True))
    subprocess.run(['cc','-Wall','-Werror','-Wno-misleading-indentation',str(p/'test.c'),'-o',str(p/'test'),*flags],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS: transient-empty recovery, confirmed end, failed confirmation, idle fast path, outgoing adoption and slot/state guards')

# Exercise the actual guards with real GObject data, including requests from
# separate call objects (screen vs headset). No fake AT request is sent on reject.
start_guard=base[base.index('    /* A hangup must settle'):base.index('    mm_obj_info (ctx->self, "processing user request to start voice call...')]
hangup=extract(base,'static void\nhandle_hangup_auth_ready (')
hangup_guard=hangup[hangup.index('    if (g_object_get_data'):hangup.index('    mm_obj_info')]
ready=extract(base,'static void\nhandle_hangup_ready (')
ready_guard=ready[ready.index('    if (g_object_get_data'):ready.index('    /* we set it')]
settle_model=r'''
#include <glib-object.h>
#define MM_CORE_ERROR 0
#define MM_CORE_ERROR_IN_PROGRESS 1
typedef struct {GObject *modem;int *invocation;} Ctx;
static int rejected,accepted;
static void mm_dbus_method_invocation_return_error_literal(int*i,int a,int b,const char*s){(*i)++;}
static void handle_start_context_free(Ctx*c){}
static void handle_hangup_context_free(Ctx*c){}
'''
settle_test=r'''
int main(void){
 GObject *modem=g_object_new(G_TYPE_OBJECT,NULL);Ctx context={modem,&rejected};Ctx*ctx=&context;
 g_object_set_data(modem,"e5-dual-sim-voice",GINT_TO_POINTER(1));
 start(modem,ctx);g_assert_cmpint(accepted,==,1);
 hangup(modem,ctx);g_assert_cmpint(accepted,==,2);
 hangup(modem,ctx);start(modem,ctx);
 g_assert_cmpint(rejected,==,2);g_assert_cmpint(accepted,==,2);
 complete(modem,ctx);start(modem,ctx);g_assert_cmpint(rejected,==,3);
 gint64 *ended=g_object_get_data(modem,"e5-voice-hangup-at");*ended-=3*G_USEC_PER_SEC;
 start(modem,ctx);g_assert_cmpint(accepted,==,3);
 g_object_unref(modem);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    code=settle_model
    for name,guard in [('start',start_guard),('hangup',hangup_guard),('complete',ready_guard)]:
        code+='static void '+name+'(GObject *modem,Ctx *ctx){\n'+guard+('accepted++;' if name!='complete' else '')+'}\n'
    (p/'test.c').write_text(code+settle_test)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gobject-2.0'],text=True))
    subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test'),*flags],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS: backend duplicate hangup rejected; redial blocked until hangup completes and 2-second settlement expires')
