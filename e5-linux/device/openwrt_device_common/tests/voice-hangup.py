#!/usr/bin/env python3
"""Exercise actual hangup command, fallback and completion with fake AT/D-Bus."""
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

source = (Path(sys.argv[1]) / 'mm-base-call.c').read_text()


def function(name):
    start = source.index('\n' + name + ' (')
    start = source.rfind('static ', 0, start)
    end = source.index('\n}\n', start) + 3
    return source[start:end]


model = r'''
#include <glib-object.h>
#include <string.h>
#define G_TASK(x) (x)
#define MM_GDBUS_CALL(x) (x)
#define mm_obj_warn(...) ((void)0)
enum { MM_CALL_STATE_ACTIVE, MM_CALL_STATE_TERMINATED, MM_CALL_STATE_REASON_TERMINATED };
typedef struct {GObject *modem;guint index;} Private;
typedef struct {Private *priv;guint state;} MMBaseCall;
typedef GObject MMBaseModem;
typedef struct {gboolean error;} GAsyncResult;
typedef struct {MMBaseCall *call;} GTask;
typedef struct {MMBaseCall*self;GObject *modem;int *invocation;} HandleHangupContext;
typedef void (*GAsyncReadyCallback)(void);
static guint global_fallback,completed,errors,released,commands;
static gchar *sent;
static GTask task;
static GTask *g_task_new(MMBaseCall*s,void*a,GAsyncReadyCallback cb,void*b){task.call=s;return &task;}
static MMBaseCall *g_task_get_source_object(GTask*t){return t->call;}
static void call_at_command(MMBaseCall*s,const gchar*cmd,guint timeout,GAsyncReadyCallback cb,void*data){g_free(sent);sent=g_strdup(cmd);commands++;}
static void chup_fallback(GTask*t){global_fallback++;}
static void mm_base_modem_at_command_finish(MMBaseModem*m,GAsyncResult*r,GError**e){if(r->error)g_set_error_literal(e,1,1,"AT rejected");}
static void g_task_return_error(GTask*t,GError*e){errors++;g_error_free(e);}
static void g_task_return_boolean(GTask*t,gboolean result){g_assert_true(result);completed++;}
static void fake_unref(void*t){released++;}
static void mm_base_call_change_state(MMBaseCall*s,guint state,guint reason){s->state=state;}
static gboolean finish(MMBaseCall*s,GAsyncResult*r,GError**e){if(r->error)g_set_error_literal(e,1,1,"AT rejected");return !r->error;}
static struct {gboolean(*hangup_finish)(MMBaseCall*,GAsyncResult*,GError**);} klass={finish};
#define MM_BASE_CALL_GET_CLASS(x) (&klass)
static void mm_dbus_method_invocation_take_error(int*i,GError*e){(*i)++;g_error_free(e);}
static void mm_gdbus_call_complete_hangup(MMBaseCall*s,int*i){completed++;}
static void handle_hangup_context_free(HandleHangupContext*c){released++;}
#define g_object_unref fake_unref
'''
test = r'''
int main(void){
 GObject *modem=g_object_new(G_TYPE_OBJECT,NULL);Private priv={modem,3};MMBaseCall call={&priv,MM_CALL_STATE_ACTIVE};
 GAsyncResult rejected={TRUE},ok={FALSE};int dbus_errors=0;HandleHangupContext ctx={&call,modem,&dbus_errors};
 g_object_set_data(modem,"e5-dual-sim-voice",GINT_TO_POINTER(1));
 for(guint i=1;i<=7;i++) {gchar expected[32];priv.index=i;call_hangup(&call,NULL,NULL);g_snprintf(expected,sizeof(expected),"+CHLD=7%u",i);g_assert_cmpstr(sent,==,expected);}
 chld_hangup_ready(modem,&rejected,&task);g_assert_cmpuint(global_fallback,==,0);g_assert_cmpuint(errors,==,1);
 g_object_set_data(modem,"e5-voice-hangup-pending",GINT_TO_POINTER(1));
 handle_hangup_ready(&call,&rejected,&ctx);g_assert_cmpuint(call.state,==,MM_CALL_STATE_ACTIVE);g_assert_cmpint(dbus_errors,==,1);
 g_assert_null(g_object_get_data(modem,"e5-voice-hangup-pending"));
 call_hangup(&call,NULL,NULL);chld_hangup_ready(modem,&ok,&task);handle_hangup_ready(&call,&ok,&ctx);g_assert_cmpuint(call.state,==,MM_CALL_STATE_TERMINATED);
 g_object_set_data(modem,"e5-dual-sim-voice",NULL);priv.index=3;call_hangup(&call,NULL,NULL);g_assert_cmpstr(sent,==,"+CHLD=13");
 chld_hangup_ready(modem,&rejected,&task);g_assert_cmpuint(global_fallback,==,1);
 call.state=MM_CALL_STATE_ACTIVE;handle_hangup_ready(&call,&rejected,&ctx);g_assert_cmpuint(call.state,==,MM_CALL_STATE_TERMINATED);
 priv.index=0;call_hangup(&call,NULL,NULL);g_assert_cmpuint(global_fallback,==,2);
 g_free(sent);return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    code = model + function('chld_hangup_ready') + function('call_hangup') + function('handle_hangup_ready') + test
    (p / 'test.c').write_text(code)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gobject-2.0'], text=True))
    subprocess.run(['cc', '-Wall', '-Werror', str(p / 'test.c'), '-o', str(p / 'test'), *flags], check=True)
    subprocess.run([str(p / 'test')], check=True)
print('PASS: stock indexed hangup, retryable errors, no unsafe global fallback, completion and generic modem compatibility')
