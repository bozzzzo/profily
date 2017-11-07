"""Class for printing reports on profiled python code."""

# Written by James Roskind
# Based on prior profile module by Sjoerd Mullender...
#   which was hacked somewhat by: Guido van Rossum

# Copyright Disney Enterprises, Inc.  All Rights Reserved.
# Licensed to PSF under a Contributor Agreement
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied.  See the License for the specific language
# governing permissions and limitations under the License.


import sys
import os
import time
import marshal
import re
from functools import cmp_to_key
import math

__all__ = ["Stats"]

class Stats:
    """This class is used for creating reports from data generated by the
    Profile class.  It is a "friend" of that class, and imports data either
    by direct access to members of Profile class, or by reading in a dictionary
    that was emitted (via marshal) from the Profile class.

    The big change from the previous Profiler (in terms of raw functionality)
    is that an "add()" method has been provided to combine Stats from
    several distinct profile runs.  Both the constructor and the add()
    method now take arbitrarily many file names as arguments.

    All the print methods now take an argument that indicates how many lines
    to print.  If the arg is a floating point number between 0 and 1.0, then
    it is taken as a decimal percentage of the available lines to be printed
    (e.g., .1 means print 10% of all available lines).  If it is an integer,
    it is taken to mean the number of lines of data that you wish to have
    printed.

    The sort_stats() method now processes some additional options (i.e., in
    addition to the old -1, 0, 1, or 2).  It takes an arbitrary number of
    quoted strings to select the sort order.  For example sort_stats('time',
    'name') sorts on the major key of 'internal function time', and on the
    minor key of 'the name of the function'.  Look at the two tables in
    sort_stats() and get_sort_arg_defs(self) for more examples.

    All methods return self, so you can string together commands like:
        Stats('foo', 'goo').strip_dirs().sort_stats('calls').\
                            print_stats(5).print_callers(5)
    """

    def __init__(self, *args, **kwds):
        # I can't figure out how to explicitly specify a stream keyword arg
        # with *args:
        #   def __init__(self, *args, stream=sys.stdout): ...
        # so I use **kwds and sqauwk if something unexpected is passed in.
        self.stream = kwds.pop("stream", sys.stdout)
        self.threshold = kwds.pop("threshold", 0.1)
        if kwds:
            keys = kwds.keys()
            keys.sort()
            extras = ", ".join(["%s=%s" % (k, kwds[k]) for k in keys])
            raise ValueError, "unrecognized keyword args: %s" % extras
        if not len(args):
            arg = None
        else:
            arg = args[0]
            args = args[1:]
        self.init(arg)
        self.add(*args)

    def init(self, arg):
        self.all_callees = None  # calc only if needed
        self.files = []
        self.fcn_list = None
        self.total_tt = 0
        self.total_calls = 0
        self.prim_calls = 0
        self.max_name_len = 0
        self.top_level = {}
        self.stats = {}
        self.sort_arg_dict = {}
        self.load_stats(arg)
        trouble = 1
        try:
            self.get_top_level_stats()
            trouble = 0
        finally:
            if trouble:
                print >> self.stream, "Invalid timing data",
                if self.files: print >> self.stream, self.files[-1],
                print >> self.stream

    def load_stats(self, arg):
        if not arg:  self.stats = {}
        elif isinstance(arg, basestring):
            f = open(arg, 'rb')
            self.stats = marshal.load(f)
            f.close()
            try:
                file_stats = os.stat(arg)
                arg = time.ctime(file_stats.st_mtime) + "    " + arg
            except:  # in case this is not unix
                pass
            self.files = [ arg ]
        elif hasattr(arg, 'create_stats'):
            arg.create_stats()
            self.stats = arg.stats
            arg.stats = {}
        if not self.stats:
            raise TypeError("Cannot create or construct a %r object from %r"
                            % (self.__class__, arg))
        return

    def get_top_level_stats(self):
        for func, (cc, nc, tt, ct, callers) in self.stats.items():
            self.total_calls += nc
            self.prim_calls  += cc
            self.total_tt    += tt
            if ("jprofile", 0, "profiler") in callers:
                self.top_level[func] = None
            if len(func_std_string(func)) > self.max_name_len:
                self.max_name_len = len(func_std_string(func))

    def add(self, *arg_list):
        if not arg_list: return self
        if len(arg_list) > 1: self.add(*arg_list[1:])
        other = arg_list[0]
        if type(self) != type(other) or self.__class__ != other.__class__:
            other = Stats(other)
        self.files += other.files
        self.total_calls += other.total_calls
        self.prim_calls += other.prim_calls
        self.total_tt += other.total_tt
        for func in other.top_level:
            self.top_level[func] = None

        if self.max_name_len < other.max_name_len:
            self.max_name_len = other.max_name_len

        self.fcn_list = None

        for func, stat in other.stats.iteritems():
            if func in self.stats:
                old_func_stat = self.stats[func]
            else:
                old_func_stat = (0, 0, 0, 0, {},)
            self.stats[func] = add_func_stats(old_func_stat, stat)
        return self

    def dump_stats(self, filename):
        """Write the profile data to a file we know how to load back."""
        f = file(filename, 'wb')
        try:
            marshal.dump(self.stats, f)
        finally:
            f.close()

    # list the tuple indices and directions for sorting,
    # along with some printable description
    sort_arg_dict_default = {
              "calls"     : (((1,-1),              ), "call count"),
              "ncalls"    : (((1,-1),              ), "call count"),
              "cumtime"   : (((3,-1),              ), "cumulative time"),
              "cumulative": (((3,-1),              ), "cumulative time"),
              "file"      : (((4, 1),              ), "file name"),
              "filename"  : (((4, 1),              ), "file name"),
              "line"      : (((5, 1),              ), "line number"),
              "module"    : (((4, 1),              ), "file name"),
              "name"      : (((6, 1),              ), "function name"),
              "nfl"       : (((6, 1),(4, 1),(5, 1),), "name/file/line"),
              "pcalls"    : (((0,-1),              ), "primitive call count"),
              "stdname"   : (((7, 1),              ), "standard name"),
              "time"      : (((2,-1),              ), "internal time"),
              "tottime"   : (((2,-1),              ), "internal time"),
              }

    def get_sort_arg_defs(self):
        """Expand all abbreviations that are unique."""
        if not self.sort_arg_dict:
            self.sort_arg_dict = dict = {}
            bad_list = {}
            for word, tup in self.sort_arg_dict_default.iteritems():
                fragment = word
                while fragment:
                    if not fragment:
                        break
                    if fragment in dict:
                        bad_list[fragment] = 0
                        break
                    dict[fragment] = tup
                    fragment = fragment[:-1]
            for word in bad_list:
                del dict[word]
        return self.sort_arg_dict

    def sort_stats(self, *field):
        if not field:
            self.fcn_list = 0
            return self
        if len(field) == 1 and isinstance(field[0], (int, long)):
            # Be compatible with old profiler
            field = [ {-1: "stdname",
                       0:  "calls",
                       1:  "time",
                       2:  "cumulative"}[field[0]] ]

        sort_arg_defs = self.get_sort_arg_defs()
        sort_tuple = ()
        self.sort_type = ""
        connector = ""
        for word in field:
            sort_tuple = sort_tuple + sort_arg_defs[word][0]
            self.sort_type += connector + sort_arg_defs[word][1]
            connector = ", "

        stats_list = []
        for func, (cc, nc, tt, ct, callers) in self.stats.iteritems():
            stats_list.append((cc, nc, tt, ct) + func +
                              (func_std_string(func), func))

        stats_list.sort(key=cmp_to_key(TupleComp(sort_tuple).compare))

        self.fcn_list = fcn_list = []
        for tuple in stats_list:
            fcn_list.append(tuple[-1])
        return self

    def reverse_order(self):
        if self.fcn_list:
            self.fcn_list.reverse()
        return self

    def strip_dirs(self):
        oldstats = self.stats
        self.stats = newstats = {}
        max_name_len = 0
        for func, (cc, nc, tt, ct, callers) in oldstats.iteritems():
            newfunc = func_strip_path(func)
            if len(func_std_string(newfunc)) > max_name_len:
                max_name_len = len(func_std_string(newfunc))
            newcallers = {}
            for func2, caller in callers.iteritems():
                newcallers[func_strip_path(func2)] = caller

            if newfunc in newstats:
                newstats[newfunc] = add_func_stats(
                                        newstats[newfunc],
                                        (cc, nc, tt, ct, newcallers))
            else:
                newstats[newfunc] = (cc, nc, tt, ct, newcallers)
        old_top = self.top_level
        self.top_level = new_top = {}
        for func in old_top:
            new_top[func_strip_path(func)] = None

        self.max_name_len = max_name_len

        self.fcn_list = None
        self.all_callees = None
        return self

    def calc_callees(self):
        if self.all_callees: return
        self.all_callees = all_callees = {}
        for func, (cc, nc, tt, ct, callers) in self.stats.iteritems():
            if not func in all_callees:
                all_callees[func] = {}
            for func2, caller in callers.iteritems():
                if not func2 in all_callees:
                    all_callees[func2] = {}
                all_callees[func2][func]  = caller
        return

    #******************************************************************
    # The following functions support actual printing of reports
    #******************************************************************

    # Optional "amount" is either a line count, or a percentage of lines.

    def eval_print_amount(self, sel, list, msg):
        new_list = list
        if isinstance(sel, basestring):
            try:
                rex = re.compile(sel)
            except re.error:
                msg += "   <Invalid regular expression %r>\n" % sel
                return new_list, msg
            new_list = []
            for func in list:
                if rex.search(func_std_string(func)):
                    new_list.append(func)
        else:
            count = len(list)
            if isinstance(sel, float) and 0.0 <= sel < 1.0:
                count = int(count * sel + .5)
                new_list = list[:count]
            elif isinstance(sel, (int, long)) and 0 <= sel < count:
                count = sel
                new_list = list[:count]
        if len(list) != len(new_list):
            msg += "   List reduced from %r to %r due to restriction <%r>\n" % (
                len(list), len(new_list), sel)

        return new_list, msg

    def get_print_list(self, sel_list):
        width = self.max_name_len
        if self.fcn_list:
            stat_list = self.fcn_list[:]
            msg = "   Ordered by: " + self.sort_type + '\n'
        else:
            stat_list = self.stats.keys()
            msg = "   Random listing order was used\n"

        for selection in sel_list:
            stat_list, msg = self.eval_print_amount(selection, stat_list, msg)

        count = len(stat_list)

        if not stat_list:
            return 0, stat_list
        print >> self.stream, '#', msg
        if count < len(self.stats):
            width = 0
            for func in stat_list:
                if  len(func_std_string(func)) > width:
                    width = len(func_std_string(func))
        return width+2, stat_list

    def print_stats(self, *amount):
        for filename in self.files:
            print >> self.stream, filename
        if self.files: print >> self.stream
        indent = ' ' * 8
        for func in self.top_level:
            print >> self.stream, indent, func_get_function_name(func)

        print >> self.stream, indent, self.total_calls, "function calls",
        if self.total_calls != self.prim_calls:
            print >> self.stream, "(%d primitive calls)" % self.prim_calls,
        print >> self.stream, "in %.3f seconds" % self.total_tt
        print >> self.stream
        width, list = self.get_print_list(amount)
        if list:
            self.print_title()
            for func in list:
                self.print_line(func)
            print >> self.stream
            print >> self.stream
        return self

    def print_callees(self, *amount):
        width, list = self.get_print_list(amount)
        if list:
            self.calc_callees()

            self.print_call_heading(width, "called...")
            for func in list:
                if func in self.all_callees:
                    self.print_call_line(width, func, self.all_callees[func])
                else:
                    self.print_call_line(width, func, {})
            print >> self.stream
            print >> self.stream
        return self

    def print_callers(self, *amount):
        width, list = self.get_print_list(amount)
        if list:
            self.print_call_heading(width, "was called by...")
            for func in list:
                cc, nc, tt, ct, callers = self.stats[func]
                self.print_caller_line(width, func, callers, "<-")
            print >> self.stream
            print >> self.stream
        return self

    def dot_callers(self, *amount):
        width, list = self.get_print_list(amount)
        if list:
            print >> self.stream, '''digraph g {
        graph [size="16,12",ranksep=.25];
        node [shape=box,fontname=Helvetica,fontsize=14];
        node [width=1.6,height=1.2,fixedsize=true];'''
            shown_callers = {}
            for func in list:
                cc, nc, tt, ct, callers = self.stats[func]
                self.print_dot_line(width, func, callers, shown_callers, self.threshold, False)
            # connect callchains that are 20 nodes apart
            for round in range(20):
                repeat = False
                for func in [func for func, shown in shown_callers.items() if not shown]:
                    repeat = True
                    cc, nc, tt, ct, callers = self.stats[func]
                    self.print_dot_line(width, func, callers, shown_callers, 0, True)
                if not repeat:
                    break
            print >> self.stream
            print >> self.stream, '}'
        return self


    def print_dot_line(self, name_size, source, call_dict, shown_callers, threshold, best):
        cc, nc, tt, ct, callers = self.stats[source]
        if not call_dict:
            print >> self.stream
            return
        if not self.total_tt:
            return
        if ct/self.total_tt < threshold and not best:
            return
        shown_callers[source] = True
        print >> self.stream, func_dot_id(source), '[ label="%s", penwidth=%.2f, style="setlinewidth(%.2f)", color="%s" ];' % (self.func_dot_string(source), self.dot_pen_width(ct), self.dot_pen_width(ct), best and "#cccccc" or self.dot_color(tt,ct) )
        clist = call_dict.items()
        clist.sort(key=lambda x:x[1][1])
        if best:
            clist = clist[:1]
        indent = ""
        for func, (ccc, cct) in clist:
            fcc, fnc, ftt, fct, fcallers = self.stats[source]
            if not best and (ct == 0.0 or cct/ct < threshold):
                continue
            print >> self.stream, func_dot_id(func), "->", func_dot_id(source), '[ label="%s (%d)", weight=%s, penwidth=%.2f, style="setlinewidth(%.2f)"];' % (f8(cct), ccc, self.dot_weight(cct), self.dot_pen_width(cct), self.dot_pen_width(cct),)
            shown_callers.setdefault(func, False)

    def func_dot_string(self, func_name):
        if func_name[:2] == ('~', 0):
            # special case for built-in functions
            name = func_name[2].replace('"','')
            if name.startswith('<') and name.endswith('>'):
                label= '{%s}' % name[1:-1]
            else:
                label= name
        else:
            label= "%s:%d\\n%s" % (func_name[0], func_name[1], str(func_name[2]).replace('"',''))

        cc, nc, tt, ct, callers = self.stats[func_name]
        label += "\\ncc:%d nc:%d\\ntt: %s\\nct:%s" % (cc, nc, f8(tt), f8(ct))
        return label


    def dot_pen_width(self, ct):
        r = ct/self.total_tt
        return 8*math.sqrt(r) + 0.2;

    def dot_weight(self, ct):
        r = ct/self.total_tt
        return 8*math.sqrt(r) + 0.2;

    def dot_color(self, tt, ct):
        if not ct:
            r = 0
        else:
            r = tt/ct
            r = math.sqrt(math.sqrt(r))
            r = int(r*255)
        return "#%02x0000"%r

    def print_call_heading(self, name_size, column_title):
        print >> self.stream, "Function ".ljust(name_size) + column_title
        # print sub-header only if we have new-style callers
        subheader = False
        for cc, nc, tt, ct, callers in self.stats.itervalues():
            if callers:
                value = callers.itervalues().next()
                subheader = isinstance(value, tuple)
                break
        if subheader:
            print >> self.stream, " "*name_size + "    ncalls  tottime  cumtime"

    def print_call_line(self, name_size, source, call_dict, arrow="->"):
        print >> self.stream, func_std_string(source).ljust(name_size) + arrow,
        if not call_dict:
            print >> self.stream
            return
        clist = call_dict.keys()
        clist.sort()
        indent = ""
        for func in clist:
            name = func_std_string(func)
            value = call_dict[func]
            if isinstance(value, tuple):
                nc, cc, tt, ct = value
                if nc != cc:
                    substats = '%d/%d' % (nc, cc)
                else:
                    substats = '%d' % (nc,)
                substats = '%s %s %s  %s' % (substats.rjust(7+2*len(indent)),
                                             f8(tt), f8(ct), name)
                left_width = name_size + 1
            else:
                substats = '%s(%r) %s' % (name, value, f8(self.stats[func][3]))
                left_width = name_size + 3
            print >> self.stream, indent*left_width + substats
            indent = " "

    def print_caller_line(self, name_size, source, call_dict, arrow="->"):
        print >> self.stream, func_std_string(source).ljust(name_size) + arrow,
        if not call_dict:
            print >> self.stream
            return
        clist = call_dict.keys()
        clist.sort()
        indent = ""
        for func in clist:
            name = func_std_string(func)
            value = call_dict[func]
            if False and isinstance(value, tuple):
                nc, cc, tt, ct = value
                if nc != cc:
                    substats = '%d/%d' % (nc, cc)
                else:
                    substats = '%d' % (nc,)
                substats = '%s %s %s  %s' % (substats.rjust(7+2*len(indent)),
                                             f8(tt), f8(ct), name)
                left_width = name_size + 1
            else:
                substats = '%s(%r) %s' % (name, value, f8(self.stats[func][3]))
                left_width = name_size + 3
            print >> self.stream, indent*left_width + substats
            indent = " "

    def print_title(self):
        print >> self.stream, '   ncalls  tottime  percall  cumtime  percall',
        print >> self.stream, 'filename:lineno(function)'

    def print_line(self, func):  # hack : should print percentages
        cc, nc, tt, ct, callers = self.stats[func]
        c = str(nc)
        if nc != cc:
            c = c + '/' + str(cc)
        print >> self.stream, c.rjust(9),
        print >> self.stream, f8(tt),
        if nc == 0:
            print >> self.stream, ' '*8,
        else:
            print >> self.stream, f8(float(tt)/nc),
        print >> self.stream, f8(ct),
        if cc == 0:
            print >> self.stream, ' '*8,
        else:
            print >> self.stream, f8(float(ct)/cc),
        print >> self.stream, func_std_string(func)

class TupleComp:
    """This class provides a generic function for comparing any two tuples.
    Each instance records a list of tuple-indices (from most significant
    to least significant), and sort direction (ascending or decending) for
    each tuple-index.  The compare functions can then be used as the function
    argument to the system sort() function when a list of tuples need to be
    sorted in the instances order."""

    def __init__(self, comp_select_list):
        self.comp_select_list = comp_select_list

    def compare (self, left, right):
        for index, direction in self.comp_select_list:
            l = left[index]
            r = right[index]
            if l < r:
                return -direction
            if l > r:
                return direction
        return 0

#**************************************************************************
# func_name is a triple (file:string, line:int, name:string)

def func_strip_path(func_name):
    filename, line, name = func_name
    return os.path.join(os.path.basename(os.path.dirname(filename)),os.path.basename(filename)), line, name

def func_get_function_name(func):
    return func[2]

def func_std_string(func_name): # match what old profile produced
    if func_name[:2] == ('~', 0):
        # special case for built-in functions
        name = func_name[2]
        if name.startswith('<') and name.endswith('>'):
            return '{%s}' % name[1:-1]
        else:
            return name
    else:
        return "%s:%d(%s)" % func_name


idmap = {}
def func_dot_id(func_name):
    return idmap.setdefault(func_name,len(idmap))

#**************************************************************************
# The following functions combine statists for pairs functions.
# The bulk of the processing involves correctly handling "call" lists,
# such as callers and callees.
#**************************************************************************

def add_func_stats(target, source):
    """Add together all the stats for two profile entries."""
    cc, nc, tt, ct, callers = source
    t_cc, t_nc, t_tt, t_ct, t_callers = target
    return (cc+t_cc, nc+t_nc, tt+t_tt, ct+t_ct,
              add_callers(t_callers, callers))

def add_callers(target, source):
    """Combine two caller lists in a single list."""
    new_callers = {}
    for func, caller in target.iteritems():
        new_callers[func] = caller
    for func, caller in source.iteritems():
        if func in new_callers:
            if isinstance(caller, tuple):
                # format used by cProfile
                new_callers[func] = tuple([i[0] + i[1] for i in
                                           zip(caller, new_callers[func])])
            else:
                # format used by profile
                new_callers[func] += caller
        else:
            new_callers[func] = caller
    return new_callers

def count_calls(callers):
    """Sum the caller statistics to get total number of calls received."""
    nc = 0
    for calls in callers.itervalues():
        nc += calls
    return nc

#**************************************************************************
# The following functions support printing of reports
#**************************************************************************

def f8(x):
    return "%8.3f" % x

#**************************************************************************
# Statistics browser added by ESR, April 2001
#**************************************************************************

def main():
    import cmd
    try:
        import readline
    except ImportError:
        pass

    class ProfileBrowser(cmd.Cmd):
        def __init__(self, profile=None):
            cmd.Cmd.__init__(self)
            self.prompt = "% "
            self.stats = None
            self.stream = sys.stdout
            if profile is not None:
                self.do_read(profile)

        def generic(self, fn, line):
            args = line.split()
            processed = []
            for term in args:
                try:
                    processed.append(int(term))
                    continue
                except ValueError:
                    pass
                try:
                    frac = float(term)
                    if frac > 1 or frac < 0:
                        print >> self.stream, "Fraction argument must be in [0, 1]"
                        continue
                    processed.append(frac)
                    continue
                except ValueError:
                    pass
                processed.append(term)
            if self.stats:
                getattr(self.stats, fn)(*processed)
            else:
                print >> self.stream, "No statistics object is loaded."
            return 0
        def generic_help(self):
            print >> self.stream, "Arguments may be:"
            print >> self.stream, "* An integer maximum number of entries to print."
            print >> self.stream, "* A decimal fractional number between 0 and 1, controlling"
            print >> self.stream, "  what fraction of selected entries to print."
            print >> self.stream, "* A regular expression; only entries with function names"
            print >> self.stream, "  that match it are printed."

        def do_add(self, line):
            if self.stats:
                self.stats.add(line)
            else:
                print >> self.stream, "No statistics object is loaded."
            return 0
        def help_add(self):
            print >> self.stream, "Add profile info from given file to current statistics object."

        def do_callees(self, line):
            return self.generic('print_callees', line)
        def help_callees(self):
            print >> self.stream, "Print callees statistics from the current stat object."
            self.generic_help()

        def do_callers(self, line):
            return self.generic('print_callers', line)
        def help_callers(self):
            print >> self.stream, "Print callers statistics from the current stat object."
            self.generic_help()

        def do_dot_callers(self, line):
            return self.generic('dot_callers', line)
        def help_dot_callers(self):
            print >> self.stream, "create dot diagram of callers statistics from the current stat object."
            self.generic_help()

        def do_EOF(self, line):
            print >> self.stream, ""
            return 1
        def help_EOF(self):
            print >> self.stream, "Leave the profile brower."

        def do_quit(self, line):
            return 1
        def help_quit(self):
            print >> self.stream, "Leave the profile brower."

        def do_read(self, line):
            if line:
                try:
                    self.stats = Stats(line)
                except IOError, args:
                    print >> self.stream, args[1]
                    return
                except Exception as err:
                    print >> self.stream, err.__class__.__name__ + ':', err
                    return
                self.prompt = line + "% "
            elif len(self.prompt) > 2:
                line = self.prompt[:-2]
                self.do_read(line)
            else:
                print >> self.stream, "No statistics object is current -- cannot reload."
            return 0
        def help_read(self):
            print >> self.stream, "Read in profile data from a specified file."
            print >> self.stream, "Without argument, reload the current file."

        def do_reverse(self, line):
            if self.stats:
                self.stats.reverse_order()
            else:
                print >> self.stream, "No statistics object is loaded."
            return 0
        def help_reverse(self):
            print >> self.stream, "Reverse the sort order of the profiling report."

        def do_sort(self, line):
            if not self.stats:
                print >> self.stream, "No statistics object is loaded."
                return
            abbrevs = self.stats.get_sort_arg_defs()
            if line and all((x in abbrevs) for x in line.split()):
                self.stats.sort_stats(*line.split())
            else:
                print >> self.stream, "Valid sort keys (unique prefixes are accepted):"
                for (key, value) in Stats.sort_arg_dict_default.iteritems():
                    print >> self.stream, "%s -- %s" % (key, value[1])
            return 0
        def help_sort(self):
            print >> self.stream, "Sort profile data according to specified keys."
            print >> self.stream, "(Typing `sort' without arguments lists valid keys.)"
        def complete_sort(self, text, *args):
            return [a for a in Stats.sort_arg_dict_default if a.startswith(text)]

        def do_stats(self, line):
            return self.generic('print_stats', line)
        def help_stats(self):
            print >> self.stream, "Print statistics from the current stat object."
            self.generic_help()

        def do_strip(self, line):
            if self.stats:
                self.stats.strip_dirs()
            else:
                print >> self.stream, "No statistics object is loaded."
        def help_strip(self):
            print >> self.stream, "Strip leading path information from filenames in the report."

        def help_help(self):
            print >> self.stream, "Show help for a given command."

        def postcmd(self, stop, line):
            if stop:
                return stop
            return None

    import sys
    if len(sys.argv) > 1:
        initprofile = sys.argv[1]
    else:
        initprofile = None
    try:
        browser = ProfileBrowser(initprofile)
        print >> browser.stream, "Welcome to the profile statistics browser."
        browser.cmdloop()
        print >> browser.stream, "Goodbye."
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
# That's all, folks.
