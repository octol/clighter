import os.path
import vim
from clang import cindex
from threading import Thread
import time
import threading

class ParsingService:
    _thread = None
    is_running= 0
    instances={}
    clang_idx = cindex.Index.create()
    def __init__(self, bufnr, bufname):
        self.tu=None
        self.applied=1
        self.sched_time = time.time()
        self.bufnr = bufnr
        self.bufname = bufname
        self.lock = threading.Lock()

    @staticmethod
    def start_parsing_loop():
        ParsingService.is_running = 1
        ParsingService._thread = Thread(target=ParsingService._parsing_worker, args=[vim.eval('g:clighter_clang_options')])
        ParsingService._thread.start()

    @staticmethod
    def stop_parsing_loop():
        ParsingService.is_running = 0
        ParsingService._thread.join()
        ParsingService._thread = None

    @staticmethod
    def _parsing_worker(args):
        while ParsingService.is_running == 1:
            try:
                for pobj in ParsingService.instances.values():
                    with pobj.lock:
                        if pobj.sched_time is not None and time.time() > pobj.sched_time:
                            if pobj.tu is None:
                                pobj.tu = ParsingService.clang_idx.parse(pobj.bufname, args, [(pobj.bufname, "\n".join(vim.buffers[pobj.bufnr]))], options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
                            else:
                                pobj.tu.reparse([(pobj.bufname, "\n".join(vim.buffers[pobj.bufnr]))], options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

                            pobj.applied = 0
                            pobj.sched_time = None
            finally:
                time.sleep(0.2)

    @staticmethod
    def join_all():
        for buf in vim.buffers:
            ext = os.path.splitext(buf.name)[1]
            if ext in ['.c', '.cpp', '.h', '.hpp', '.m']:
                ParsingService.instances[buf.number] = ParsingService(buf.number, buf.name) 

    @staticmethod
    def join():
        ft = vim.eval("&filetype") 
        if ft in ["c", "cpp", "objc"]:
            ParsingService.instances[vim.current.buffer.number] = ParsingService(vim.current.buffer.number, vim.current.buffer.name) 

    @staticmethod
    def reset_sched():
        pobj = ParsingService.instances.get(vim.current.buffer.number)
        if pobj is None:
            return

        with pobj.lock:
            pobj.sched_time = time.time() + 0.5


if vim.eval("g:clighter_libclang_file"):
    cindex.Config.set_library_file(vim.eval("g:clighter_libclang_file"))

#def try_highlight2():
    #vim_win_top = int(vim.eval("line('w0')"))
    #vim_win_bottom = int(vim.eval("line('w$')"))
    #clighter_window = vim.current.window.vars["clighter_window"]

    #pobj = ParsingService.instances.get(vim.current.buffer.number)
    #if pobj is None:
        #return

    #with pobj.lock:
        #if pobj.tu is None:
            #return

        #file = pobj.tu.get_file(vim.current.buffer.name)
        #if file == None: # should not happened
            #return

        #dfs(pobj.tu.cursor, vim_win_top, vim_win_bottom)

#def bfs(c, top, bottom, queue):
    #if c.location.line >= top and c.location.line <= bottom:
        #draw_token(c)

    #queue.put(c.get_children())

    #while not queue.empty():
        #curs = queue.get()
        #for cur in curs:
            #if cur.location.line >= top and cur.location.line <= bottom:
                #draw_token(cur)

            #queue.put(cur.get_children())


#def dfs(cursor, top, bottom):
    #if cursor.location.line >= top and cursor.location.line <= bottom:
        #draw_token(cursor)

    #for c in cursor.get_children():
        #dfs(c, top, bottom)


def _highlight_window():
    window_size = int(vim.eval('g:clighter_window_size')) * 100

    vim_win_top = int(vim.eval("line('w0')"))
    vim_win_bottom = int(vim.eval("line('w$')"))
    clighter_window = vim.current.window.vars["clighter_window"]

    pobj = ParsingService.instances.get(vim.current.buffer.number)
    if pobj is None:
        return

    with pobj.lock:
        if pobj.tu is None:
            return

        file = pobj.tu.get_file(vim.current.buffer.name)
        if file == None: # should not happened
            return

        buflinenr = len(vim.current.buffer);
        if (window_size < 0):
            vim.command("let w:clighter_window=[0, %d]" % buflinenr)
            tokens = pobj.tu.cursor.get_tokens()
        else:
            top_linenr = max(vim_win_top - window_size, 1);
            bottom_linenr = min(vim_win_bottom + window_size, buflinenr)
            vim.command("let w:clighter_window=[%d, %d]" %(top_linenr, bottom_linenr))
            range = cindex.SourceRange.from_locations(cindex.SourceLocation.from_position(pobj.tu, file, top_linenr, 1), cindex.SourceLocation.from_position(pobj.tu, file, bottom_linenr, 1))
            tokens = pobj.tu.get_tokens(extent=range)

        vim_cursor = None
        if int(vim.eval("s:cursor_decl_ref_hl_on")) == 1:
            (row, col) = vim.current.window.cursor
            vim_cursor = cindex.Cursor.from_location(pobj.tu, cindex.SourceLocation.from_position(pobj.tu, file, row, col + 1)) # cusor under vim-cursor

        def_cursor = None
        if vim_cursor is not None:
            def_cursor = get_definition_or_declaration(vim_cursor)

        vim.command("call s:clear_match(['CursorDefRef'])")
        invalid = vim_win_top < clighter_window[0] or vim_win_bottom > clighter_window[1] or pobj.applied == 0
        if invalid:
            vim.command("call s:clear_match(['MacroInstantiation', 'StructDecl', 'ClassDecl', 'EnumDecl', 'EnumConstantDecl', 'TypeRef', 'EnumDeclRefExpr'])")
            ParsingService.instances[vim.current.buffer.number].applied = 1

        if def_cursor is not None and def_cursor.location.file.name == file.name and def_cursor.kind.is_preprocessing():
            _vim_matchaddpos('CursorDefRef', def_cursor.location.line, def_cursor.location.column, len(get_spelling_or_displayname(def_cursor)), -1)

        for t in tokens:
            """ Do semantic highlighting'
            """
            if t.kind.value == 2:
                t_tu_cursor = cindex.Cursor.from_location(pobj.tu, cindex.SourceLocation.from_position(pobj.tu, file, t.location.line, t.location.column))

                if invalid:
                    draw_token(t)

                """ Do definition/reference highlighting'
                """
                if def_cursor is not None and def_cursor.location.file.name == file.name:
                    t_def_cursor = get_definition_or_declaration(t_tu_cursor)
                    if t_def_cursor is not None and t_def_cursor == def_cursor:
                        _vim_matchaddpos('CursorDefRef', t.location.line, t.location.column, len(t.spelling), -1)



def get_spelling_or_displayname(cursor):
    if cursor.spelling is not None:
        return cursor.spelling

    return cursor.displayname


def get_definition_or_declaration(cursor):
    if cursor.kind == cindex.CursorKind.MACRO_DEFINITION:
        return cursor

    def_cur = cursor.get_definition()
    if def_cur is None:
        def_cur = cursor.referenced

    if def_cur is not None and vim.eval('expand("<cword>")') != get_spelling_or_displayname(def_cur):
        def_cur = None

    return def_cur

def draw_token(token):
    if token.kind == cindex.CursorKind.MACRO_INSTANTIATION:
        _vim_matchaddpos('MacroInstantiation', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.STRUCT_DECL:
        _vim_matchaddpos('StructDecl', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.CLASS_DECL:
        _vim_matchaddpos('ClassDecl', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.ENUM_DECL:
        _vim_matchaddpos('EnumDecl', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
        _vim_matchaddpos('EnumConstantDecl', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.TYPE_REF:
        _vim_matchaddpos('TypeRef', token.location.line, token.location.column, len(token.spelling), -2)
    elif token.kind == cindex.CursorKind.DECL_REF_EXPR and token.type.kind == cindex.TypeKind.ENUM:
        _vim_matchaddpos('EnumDeclRefExpr', token.location.line, token.location.column, len(token.spelling), -2)

def search_and_rename_global_symbol(sym_name, kind, new_name):
    tu = ParsingService.clang_idx.parse(vim.current.buffer.name, vim.eval('g:clighter_clang_options'), [(vim.current.buffer.name, "\n".join(vim.buffers[vim.current.buffer.number]))], options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    locs = []

    cursor = _search_global_cursor(tu, tu.cursor, sym_name, kind)
    if cursor is None:
        return

    if cursor.kind == cindex.CursorKind.MACRO_DEFINITION:
        locs.append(cursor.location)

    _search_cursors_with_define(tu.cursor, cursor, locs)

    _vim_replace(locs, sym_name, new_name)


def rename():
    tu = ParsingService.clang_idx.parse(vim.current.buffer.name, vim.eval('g:clighter_clang_options'), [(vim.current.buffer.name, "\n".join(vim.buffers[vim.current.buffer.number]))], options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    file = cindex.File.from_name(tu, vim.current.buffer.name)
    (row, col) = vim.current.window.cursor
    vim_cursor = cindex.Cursor.from_location(tu, cindex.SourceLocation.from_position(tu, file, row, col + 1)) # cusor under vim-cursor
    locs = []

    def_cur = get_definition_or_declaration(vim_cursor)
    if def_cur is None or def_cur.location.file.name != file.name:
        return

    vim.command("let a:new_name = input('rename {0} to: ')".format(def_cur.spelling))
    
    if not vim.eval("a:new_name"):
        return

    if def_cur.kind.is_preprocessing():
        locs.append(def_cur.location)

    _search_cursors_with_define(tu.cursor, def_cur, locs)

    _vim_replace(locs, get_spelling_or_displayname(def_cur), vim.eval("a:new_name"))
    #search_and_rename_global_symbol("foo", cindex.CursorKind.FUNCTION_DECL, "bar")


def _search_cursors_with_define(cursor, def_cur, locs):
    cur_def = get_definition_or_declaration(cursor)
    if cur_def is not None and cur_def == def_cur:
        locs.append(cursor.location)

    for c in cursor.get_children():
        _search_cursors_with_define(c, def_cur, locs)


def _search_global_cursor(tu, cursor, symbol, kind):
    if get_spelling_or_displayname(cursor) == symbol and cursor.kind == kind and cursor.semantic_parent.displayname == vim.current.buffer.name:
        return cursor

    for c in cursor.get_children():
        result = _search_global_cursor(tu, c, symbol, kind)
        if result is not None:
            return result

    return None

def _get_identifier_token(cursor):
    tokens = cursor.get_tokens()
    for t in tokens:
        if t.kind.value == 2:
            return t

    return None

def _vim_replace(locs, old, new):
    if not locs:
        return

    pattern = ""

    for loc in locs:
        if pattern:
            pattern += "\|"

        pattern += "\%" + str(loc.line) + "l" + "\%>" + str(loc.column - 1) + "v\%<" + str(loc.column + len(old) + 1) + "v" + old 

    cmd = ":%s/" + pattern + "/" + new + "/gI"

    vim.command(cmd)


def _vim_matchaddpos(group, line, col, len, priority):
    vim.command("call matchaddpos('{0}', [[{1}, {2}, {3}]], {4})".format(group, line, col, len, priority))
    # vim.command("call add(w:semantic_list, matchadd('{0}', '\%{1}l\%>{2}c.\%<{3}c', -1))".format(group, t.location.line, t.location.column-1, t.location.column+len(t.spelling) + 1));
