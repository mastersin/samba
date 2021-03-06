# based on playground/evil in the waf svn tree

import os, datetime, fnmatch
from waflib import Scripting, Utils, Options, Logs, Errors
from waflib import ConfigSet, Context
from samba_utils import LOCAL_CACHE, os_path_relpath

def run_task(t, k):
    '''run a single build task'''
    ret = t.run()
    if ret:
        raise Errors.WafError("Failed to build %s: %u" % (k, ret))


def run_named_build_task(cmd):
    '''run a named build task, matching the cmd name using fnmatch
    wildcards against inputs and outputs of all build tasks'''
    bld = fake_build_environment(info=False)
    found = False
    cwd_node = bld.root.find_dir(os.getcwd())
    top_node = bld.root.find_dir(bld.srcnode.abspath())

    cmd = os.path.normpath(cmd)

    # cope with builds of bin/*/*
    if os.path.islink(cmd):
        cmd = os_path_relpath(os.readlink(cmd), os.getcwd())

    if cmd[0:12] == "bin/default/":
        cmd = cmd[12:]

    for g in bld.task_manager.groups:
        for attr in ['outputs', 'inputs']:
            for t in g.tasks:
                s = getattr(t, attr, [])
                for k in s:
                    relpath1 = k.relpath_gen(cwd_node)
                    relpath2 = k.relpath_gen(top_node)
                    if (fnmatch.fnmatch(relpath1, cmd) or
                        fnmatch.fnmatch(relpath2, cmd)):
                        t.position = [0,0]
                        print(t.display())
                        run_task(t, k)
                        found = True


    if not found:
        raise Errors.WafError("Unable to find build target matching %s" % cmd)


def rewrite_compile_targets():
    '''cope with the bin/ form of compile target'''
    if not Options.options.compile_targets:
        return

    bld = fake_build_environment(info=False)
    targets = LOCAL_CACHE(bld, 'TARGET_TYPE')
    tlist = []

    for t in Options.options.compile_targets.split(','):
        if not os.path.islink(t):
            tlist.append(t)
            continue
        link = os.readlink(t)
        list = link.split('/')
        for name in [list[-1], '/'.join(list[-2:])]:
            if name in targets:
                tlist.append(name)
                continue
    Options.options.compile_targets = ",".join(tlist)



def wildcard_main(missing_cmd_fn):
    '''this replaces main from Scripting, allowing us to override the
       behaviour for unknown commands

       If a unknown command is found, then missing_cmd_fn() is called with
       the name of the requested command
       '''
    Scripting.commands = Options.arg_line[:]

    # rewrite the compile targets to cope with the bin/xx form
    rewrite_compile_targets()

    while Scripting.commands:
        x = Scripting.commands.pop(0)

        ini = datetime.datetime.now()
        if x == 'configure':
            fun = Scripting.configure
        elif x == 'build':
            fun = Scripting.build
        else:
            fun = getattr(Utils.g_module, x, None)

        # this is the new addition on top of main from Scripting.py
        if not fun:
            missing_cmd_fn(x)
            break

        ctx = getattr(Utils.g_module, x + '_context', Utils.Context)()

        if x in ['init', 'shutdown', 'dist', 'distclean', 'distcheck']:
            try:
                fun(ctx)
            except TypeError:
                fun()
        else:
            fun(ctx)

        ela = ''
        if not Options.options.progress_bar:
            ela = ' (%s)' % Utils.get_elapsed_time(ini)

        if x != 'init' and x != 'shutdown':
            Logs.info('%r finished successfully%s' % (x, ela))

        if not Scripting.commands and x != 'shutdown':
            Scripting.commands.append('shutdown')




def fake_build_environment(info=True, flush=False):
    """create all the tasks for the project, but do not run the build
    return the build context in use"""
    bld = getattr(Context.g_module, 'build_context', Utils.Context)()
    bld = Scripting.check_configured(bld)

    Options.commands['install'] = False
    Options.commands['uninstall'] = False

    bld.is_install = 0 # False

    try:
        proj = ConfigSet.ConfigSet(Options.lockfile)
    except IOError:
        raise Errors.WafError("Project not configured (run 'waf configure' first)")

    bld.load_envs()

    if info:
        Logs.info("Waf: Entering directory `%s'" % bld.bldnode.abspath())
    bld.add_subdirs([os.path.split(Context.g_module.root_path)[0]])

    bld.pre_build()
    if flush:
        bld.flush()
    return bld

