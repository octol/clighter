import vim
import clighter_helper
from clang import cindex
import clang_service

DEF_REF_PRI = -11
SYNTAX_PRI = -12


def clear_highlight():
    __vim_clear_match_pri(DEF_REF_PRI, SYNTAX_PRI)
    highlight_window.hl_tick = 0
    highlight_window.syntactic_range = None
    highlight_window.highlighted_define_cur = None


def clear_def_ref():
    __vim_clear_match_pri(DEF_REF_PRI)
    highlight_window.highlighted_define_cur = None


def highlight_window(clang_service, extend=50):
    tu_ctx = clang_service.get_tu_ctx(vim.current.buffer.name)
    if tu_ctx is None:
        clear_highlight()
        return

    tu = tu_ctx.translation_unit
    if tu is None:
        clear_highlight()
        return

    top = vim.bindeval("line('w0')")
    bottom = vim.bindeval("line('w$')")

    draw_syntax = False
    draw_def_ref = False

    if highlight_window.hl_tick < clang_service.parse_tick \
            or highlight_window.syntactic_range is None \
            or top < highlight_window.syntactic_range[0] \
            or bottom > highlight_window.syntactic_range[1]:
        draw_syntax = True
        __vim_clear_match_pri(SYNTAX_PRI)
        highlight_window.hl_tick = clang_service.parse_tick

    if vim.vars["ClighterCursorHL"] == 1:
        vim_cursor, def_cursor = clighter_helper.get_vim_cursor_and_def(tu_ctx)

        if highlight_window.highlighted_define_cur is not None \
                and (def_cursor is None
                     or highlight_window.highlighted_define_cur != def_cursor):
            __vim_clear_match_pri(DEF_REF_PRI)

        if def_cursor is not None \
                and (highlight_window.highlighted_define_cur is None
                     or highlight_window.highlighted_define_cur != def_cursor):
            draw_def_ref = True

            # special case for preprocessor
            if def_cursor.kind.is_preprocessing() \
                    and def_cursor.location.file.name == vim.current.buffer.name:
                __vim_matchaddpos(
                    group='clighterCursorDefRef',
                    line=def_cursor.location.line,
                    col=def_cursor.location.column,
                    len=len(
                        clighter_helper.get_spelling_or_displayname(
                            def_cursor)),
                    priority=DEF_REF_PRI
                )

        highlight_window.highlighted_define_cur = def_cursor

    if not draw_syntax and not draw_def_ref:
        return

    target_range = [top, bottom]

    if draw_syntax:
        buflinenr = len(vim.current.buffer)
        target_range = [
            max(top - extend, 1),
            min(bottom + extend, buflinenr)
        ]
        highlight_window.syntactic_range = target_range

    file = tu.get_file(tu_ctx.bufname)
    tokens = tu.get_tokens(
        extent=cindex.SourceRange.from_locations(
            cindex.SourceLocation.from_position(
                tu, file,
                line=target_range[0],
                column=1
            ),
            cindex.SourceLocation.from_position(
                tu, file,
                line=target_range[1] + 1,
                column=1
            )
        )
    )

    for t in tokens:
        """ Do semantic highlighting'
        """
        if t.kind.value != 2:
            continue

        t_cursor = cindex.Cursor.from_location(
            tu,
            cindex.SourceLocation.from_position(
                tu, file,
                t.location.line,
                t.location.column
            )
        )  # cursor under vim

        if draw_syntax:
            __draw_token(
                line=t.location.line,
                col=t.location.column,
                len=len(t.spelling),
                kind=t_cursor.kind,
                type=t_cursor.type.kind
            )

        """ Do definition/reference highlighting'
        """
        if draw_def_ref:
            t_def_cursor = clighter_helper.get_semantic_definition(t_cursor)
            if t_def_cursor is not None \
                    and t_def_cursor == highlight_window.highlighted_define_cur:
                __vim_matchaddpos(
                    group='clighterCursorDefRef',
                    line=t.location.line,
                    col=t.location.column,
                    len=len(t.spelling),
                    priority=DEF_REF_PRI
                )


highlight_window.highlighted_define_cur = None
highlight_window.hl_tick = 0
highlight_window.syntactic_range = None


def __draw_token(line, col, len, kind, type):
    highlight_groups = vim.vars['clighter_highlight_groups']

    def draw(group):
        if group in highlight_groups:
            __vim_matchaddpos(group, line, col, len, SYNTAX_PRI)

    if kind == cindex.CursorKind.MACRO_INSTANTIATION:
        draw('clighterMacroInstantiation')
    elif kind == cindex.CursorKind.STRUCT_DECL:
        draw('clighterStructDecl')
    elif kind == cindex.CursorKind.CLASS_DECL:
        draw('clighterClassDecl')
    elif kind == cindex.CursorKind.ENUM_DECL:
        draw('clighterEnumDecl')
    elif kind == cindex.CursorKind.ENUM_CONSTANT_DECL:
        draw('clighterEnumConstantDecl')
    elif kind == cindex.CursorKind.TYPE_REF:
        draw('clighterTypeRef')
    elif kind == cindex.CursorKind.FUNCTION_DECL:
        draw('clighterFunctionDecl')
    elif kind == cindex.CursorKind.MEMBER_REF_EXPR:
        draw('clighterMemberRefExpr')
    elif kind in (cindex.CursorKind.NAMESPACE_REF, cindex.CursorKind.NAMESPACE):
        draw('clighterNamespace')
    elif kind == cindex.CursorKind.DECL_REF_EXPR:
        if type == cindex.TypeKind.ENUM:
            draw('clighterDeclRefExprEnum')
        elif type == cindex.TypeKind.FUNCTIONPROTO:
            draw('clighterDeclRefExprCall')


def __vim_matchaddpos(group, line, col, len, priority):
    cmd = "call matchaddpos('{0}', [[{1}, {2}, {3}]], {4})"
    vim.command(cmd.format(group, line, col, len, priority))


def __vim_clear_match_pri(*priorities):
    cmd = "call s:clear_match_pri({0})"
    vim.command(cmd.format(list(priorities)))
