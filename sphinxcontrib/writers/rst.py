# -*- coding: utf-8 -*-
"""
    sphinxcontrib.writers.rst
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Custom docutils writer for ReStructuredText.

    :copyright: Copyright 2012-2021 by Freek Dijkstra and contributors.
    :license: BSD, see LICENSE.txt for details.

    Based on sphinx.writers.text.TextWriter, copyright 2007-2014 by the Sphinx team.
"""

from __future__ import (print_function, unicode_literals, absolute_import)

import os
import sys
import textwrap
import logging

# Added
import posixpath
import re
from itertools import chain
from docutils.utils import column_width
from ..restbuilder import include

from docutils import nodes, writers
from docutils.nodes import fully_normalize_name, whitespace_normalize_name, Text

from sphinx import addnodes
from sphinx.locale import _
from sphinx.writers.text import Cell, Table, MAXWIDTH, STDINDENT


def escape_uri(uri):
    if uri.endswith('_'):
        uri = uri[:-1] + '\\_'
    return uri

class _Table(Table):

    def __str__(self):
        out = []
        self.rewrap()

        def writesep(char="-", lineno=None):
            """Called on the line *before* lineno.
            Called with no *lineno* for the last sep.
            """
            out: List[str] = []
            for colno, width in enumerate(self.measured_widths):
                if (
                    lineno is not None and
                    lineno > 0 and
                    self[lineno, colno] is self[lineno - 1, colno]
                ):
                    out.append(" " * (width + 2))
                else:
                    out.append(char * (width + 2))
            head = "+" if out[0][0] == "-" or "=" else "|"
            tail = "+" if out[-1][0] == "-" or out[0][0] == "=" else "|"
            glue = [
                "+" if left[0] == "-" or left[0] == "=" or right[0] == "-" or right[0] == "=" else "|"
                for left, right in zip(out, out[1:])
            ]
            glue.append(tail)
            return head + "".join(chain.from_iterable(zip(out, glue)))

        for lineno, line in enumerate(self.lines):
            if self.separator and lineno == self.separator:
                out.append(writesep("=", lineno))
            else:
                out.append(writesep("-", lineno))
            for physical_line in range(self.physical_lines_for_line(line)):
                linestr = ["|"]
                for colno, cell in enumerate(line):
                    if cell.col != colno:
                        continue
                    if lineno != cell.row:
                        physical_text = ""
                    elif physical_line >= len(cell.wrapped):
                        physical_text = ""
                    else:
                        physical_text = cell.wrapped[physical_line]
                    adjust_len = len(physical_text) - column_width(physical_text)
                    linestr.append(
                        " " +
                        physical_text.ljust(
                            self.cell_width(cell, self.measured_widths) + 1 + adjust_len
                        ) + "|"
                    )
                out.append("".join(linestr))
        out.append(writesep("-"))
        return "\n".join(out)


class RstWriter(writers.Writer):
    supported = ('text',)
    settings_spec = ('No options here.', '', ())
    settings_defaults = {}

    output = None

    def __init__(self, builder):
        writers.Writer.__init__(self)
        self.builder = builder

    def translate(self):
        visitor = RstTranslator(self.document, self.builder)
        self.document.walkabout(visitor)
        self.output = visitor.body


class RstTranslator(nodes.NodeVisitor):
    sectionchars = '*=-~"+`'

    _base_admonitions = (
        'attention',
        'caution',
        'danger',
        'error',
        'hint',
        'important',
        'note',
        'tip',
        'warning',
        )

    def __init__(self, document, builder):
        nodes.NodeVisitor.__init__(self, document)

        self.document = document
        self.builder = builder

        newlines = builder.config.text_newlines
        if newlines == 'windows':
            self.nl = '\r\n'
        elif newlines == 'native':
            self.nl = os.linesep
        else:
            self.nl = '\n'
        self.sectionchars = builder.config.text_sectionchars
        self.states = [[]]
        self.stateindent = [0]
        self.list_counter = []
        self.list_formatter = []
        self.sectionlevel = 0
        self.table = None
        if self.builder.config.rst_indent:
            self.indent = self.builder.config.rst_indent
        else:
            self.indent = STDINDENT
        self.wrapper = textwrap.TextWrapper(width=MAXWIDTH, break_long_words=False, break_on_hyphens=False)

    def log_warning(self, message):
        logger = logging.getLogger("sphinxcontrib.writers.rst")
        if len(logger.handlers) == 0:
            # Logging is not yet configured. Configure it.
            logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(levelname)-8s %(message)s')
            logger = logging.getLogger("sphinxcontrib.writers.rst")
        logger.warning(message)

    def log_unknown(self, type, node):
        self.log_warning("%s(%s) unsupported formatting" % (type, node))

    def wrap(self, text, width=MAXWIDTH):
        self.wrapper.width = width
        return self.wrapper.wrap(text)

    def add_text(self, text):
        self.states[-1].append((-1, text))
    def new_state(self, indent=STDINDENT):
        self.states.append([])
        self.stateindent.append(indent)
    def end_state(self, wrap=True, end=[''], first=None):
        content = self.states.pop()
        width = max(MAXWIDTH//3, MAXWIDTH - sum(self.stateindent))
        indent = self.stateindent.pop()
        result = []
        toformat = []
        def do_format():
            if not toformat:
                return
            if wrap:
                res = self.wrap(''.join(toformat), width=width)
            else:
                res = ''.join(toformat).splitlines()
            if end:
                res += end
            result.append((indent, res))
        for itemindent, item in content:
            if itemindent == -1:
                toformat.append(item)
            else:
                do_format()
                result.append((indent + itemindent, item))
                toformat = []
        do_format()
        if first is not None and result:
            itemindent, item = result[0]
            if item:
                result.insert(0, (itemindent - indent, [first + item[0]]))
                result[1] = (itemindent, item[1:])
        self.states[-1].extend(result)

    def visit_document(self, node):
        self.new_state(0)
    def depart_document(self, node):
        self.end_state()
        self.body = self.nl.join(line and (' '*indent + line)
                                 for indent, lines in self.states[0]
                                 for line in lines)
        # TODO: add header/footer?

    def visit_highlightlang(self, node):
        raise nodes.SkipNode

    def visit_section(self, node):
        self._title_char = self.sectionchars[self.sectionlevel]
        self.sectionlevel += 1
    def depart_section(self, node):
        self.sectionlevel -= 1

    def visit_topic(self, node):
        self.new_state(0)
    def depart_topic(self, node):
        self.end_state()

    visit_sidebar = visit_topic
    depart_sidebar = depart_topic

    def visit_rubric(self, node):
        pass

    def depart_rubric(self, node):
        pass

    def visit_compound(self, node):
        # self.log_unknown("compount", node)
        pass
    def depart_compound(self, node):
        pass

    def visit_glossary(self, node):
        # self.log_unknown("glossary", node)
        pass
    def depart_glossary(self, node):
        pass

    def visit_title(self, node):
        # if isinstance(node.parent, nodes.Admonition):
        #     raise nodes.SkipNode
        self.new_state(0)
    def depart_title(self, node):
        if isinstance(node.parent, nodes.section):
            char = self._title_char
        else:
            char = '^'
        text = ''.join(x[1] for x in self.states.pop() if x[0] == -1)
        self.stateindent.pop()
        self.states[-1].append((0, ['', text, '%s' % (char * len(text)), '']))

    def visit_subtitle(self, node):
        # self.log_unknown("subtitle", node)
        pass
    def depart_subtitle(self, node):
        pass

    def visit_attribution(self, node):
        self.add_text('-- ')
    def depart_attribution(self, node):
        pass

    def visit_desc(self, node):
        self.new_state(0)
    def depart_desc(self, node):
        self.end_state()

    def visit_desc_signature(self, node):
        if node.parent['objtype'] in ('class', 'exception', 'method', 'function'):
            self.add_text('**')
        else:
            self.add_text('``')
    def depart_desc_signature(self, node):
        if node.parent['objtype'] in ('class', 'exception', 'method', 'function'):
            self.add_text('**')
        else:
            self.add_text('``')

    def visit_desc_name(self, node):
        # self.log_unknown("desc_name", node)
        pass
    def depart_desc_name(self, node):
        pass

    def visit_desc_addname(self, node):
        # self.log_unknown("desc_addname", node)
        pass
    def depart_desc_addname(self, node):
        pass

    def visit_desc_type(self, node):
        # self.log_unknown("desc_type", node)
        pass
    def depart_desc_type(self, node):
        pass

    def visit_desc_returns(self, node):
        self.add_text(' -> ')
    def depart_desc_returns(self, node):
        pass

    def visit_desc_parameterlist(self, node):
        self.add_text('(')
        self.first_param = 1
    def depart_desc_parameterlist(self, node):
        self.add_text(')')

    def visit_desc_parameter(self, node):
        if not self.first_param:
            self.add_text(', ')
        else:
            self.first_param = 0
        self.add_text(node.astext())
        raise nodes.SkipNode

    def visit_desc_optional(self, node):
        self.add_text('[')
    def depart_desc_optional(self, node):
        self.add_text(']')

    def visit_desc_annotation(self, node):
        content = node.astext()
        if len(content) > MAXWIDTH:
            h = int(MAXWIDTH/3)
            content = content[:h] + " ... " + content[-h:]
            self.add_text(content)
            raise nodes.SkipNode
    def depart_desc_annotation(self, node):
        pass

    def visit_refcount(self, node):
        pass
    def depart_refcount(self, node):
        pass

    def visit_desc_content(self, node):
        self.new_state(self.indent)
    def depart_desc_content(self, node):
        self.end_state()

    def visit_figure(self, node):
        self.new_state(self.indent)
    def depart_figure(self, node):
        self.end_state()

    def visit_caption(self, node):
        # self.log_unknown("caption", node)
        pass
    def depart_caption(self, node):
        pass

    def visit_productionlist(self, node):
        self.new_state(self.indent)
        names = []
        for production in node:
            names.append(production['tokenname'])
        maxlen = max(len(name) for name in names)
        for production in node:
            if production['tokenname']:
                self.add_text(production['tokenname'].ljust(maxlen) + ' ::=')
                lastname = production['tokenname']
            else:
                self.add_text('%s    ' % (' '*len(lastname)))
            self.add_text(production.astext() + self.nl)
        self.end_state(wrap=False)
        raise nodes.SkipNode

    def visit_seealso(self, node):
        self.new_state(self.indent)
    def depart_seealso(self, node):
        self.end_state(first='')

    def visit_footnote(self, node):
        self._footnote = node.children[0].astext().strip()
        self.new_state(len(self._footnote) + self.indent)
    def depart_footnote(self, node):
        self.end_state(first='[%s] ' % self._footnote)

    def visit_citation(self, node):
        if len(node) and isinstance(node[0], nodes.label):
            self._citlabel = node[0].astext()
        else:
            self._citlabel = ''
        self.new_state(len(self._citlabel) + self.indent)
    def depart_citation(self, node):
        self.end_state(first='[%s] ' % self._citlabel)

    def visit_label(self, node):
        raise nodes.SkipNode

    # TODO: option list could use some better styling

    def visit_option_list(self, node):
        # self.log_unknown("option_list", node)
        pass
    def depart_option_list(self, node):
        pass

    def visit_option_list_item(self, node):
        self.new_state(0)
    def depart_option_list_item(self, node):
        self.end_state()

    def visit_option_group(self, node):
        self._firstoption = True
    def depart_option_group(self, node):
        self.add_text('     ')

    def visit_option(self, node):
        if self._firstoption:
            self._firstoption = False
        else:
            self.add_text(', ')
    def depart_option(self, node):
        pass

    def visit_option_string(self, node):
        # self.log_unknown("option_string", node)
        pass
    def depart_option_string(self, node):
        pass

    def visit_option_argument(self, node):
        self.add_text(node['delimiter'])
    def depart_option_argument(self, node):
        pass

    def visit_description(self, node):
        # self.log_unknown("description", node)
        pass
    def depart_description(self, node):
        pass

    def visit_tabular_col_spec(self, node):
        raise nodes.SkipNode
    
    def depart_tabular_col_spec(self, node):
        pass

    def visit_colspec(self, node):
        self.table.colwidth.append(node["colwidth"])
        raise nodes.SkipNode

    def visit_tgroup(self, node):
        pass
    def depart_tgroup(self, node):
        pass

    def visit_thead(self, node):
        pass
    def depart_thead(self, node):
        pass

    def visit_tbody(self, node):
        self.table.set_separator()
    def depart_tbody(self, node):
        pass

    def visit_row(self, node):
        if self.table.lines:
            self.table.add_row()
    def depart_row(self, node):
        pass

    def visit_entry(self, node):
        self.entry = Cell(
            rowspan=node.get("morerows", 0) + 1, colspan=node.get("morecols", 0) + 1
        )
        self.new_state(0)
    def depart_entry(self, node):
        text = self.nl.join(self.nl.join(x[1]) for x in self.states.pop())
        self.stateindent.pop()
        self.entry.text = text
        self.table.add_cell(self.entry)
        self.entry = None

    def visit_table(self, node):
        if self.table:
            self.log_warning('Nested tables are not supported.')
        self.new_state(0)
        self.table = _Table()

    def depart_table(self, node):
        self.add_text(str(self.table))
        self.table = None
        self.end_state(wrap=False)

    def visit_acks(self, node):
        self.new_state(0)
        self.add_text(', '.join(n.astext() for n in node.children[0].children)
                      + '.')
        self.end_state()
        raise nodes.SkipNode

    def visit_image(self, node):
        self.new_state(0)
        if 'uri' in node:
            self.add_text(_('.. image:: /%s') % escape_uri(node['uri']))
        elif 'target' in node.attributes:
            self.add_text(_('.. image: /%s') % node['target'])
        elif 'alt' in node.attributes:
            self.add_text(_('[image: %s]') % node['alt'])
        else:
            self.add_text(_('[image]'))
        indent = self.indent * ' '
        if 'align' in node.attributes:
            self.add_text(_(self.nl + indent + ((':align: %s') % node['align'])))
        if 'width' in node.attributes:
            self.add_text(_(self.nl + indent + ((':width: %s') % node['width'])))
        self.end_state(wrap=False)
        raise nodes.SkipNode

    def visit_transition(self, node):
        indent = sum(self.stateindent)
        self.new_state(0)
        self.add_text('=' * (MAXWIDTH - indent))
        self.end_state()
        raise nodes.SkipNode

    def visit_bullet_list(self, node):
        def bullet_list_format(counter):
            return '-'
        self.list_counter.append(-1)  # TODO: just 0 is fine.
        self.list_formatter.append(bullet_list_format)
    def depart_bullet_list(self, node):
        self.list_counter.pop()
        self.list_formatter.pop()

    def visit_enumerated_list(self, node):
        def enumerated_list_format(counter):
            return str(counter) + '.'
        self.list_counter.append(0)
        self.list_formatter.append(enumerated_list_format)
    def depart_enumerated_list(self, node):
        self.list_counter.pop()
        self.list_formatter.pop()

    def visit_list_item(self, node):
        self.list_counter[-1] += 1
        bullet_formatter = self.list_formatter[-1]
        bullet = bullet_formatter(self.list_counter[-1])
        indent = max(self.indent, len(bullet) + 1)
        self.new_state(indent)
    def depart_list_item(self, node):
        # formatting to make the string `self.stateindent[-1]` chars long.
        format = '%%-%ds' % (self.stateindent[-1])
        bullet_formatter = self.list_formatter[-1]
        bullet = format % bullet_formatter(self.list_counter[-1])
        self.end_state(first=bullet, end=None)

    def visit_definition_list(self, node):
        pass
    def depart_definition_list(self, node):
        pass

    def visit_definition_list_item(self, node):
        self._li_has_classifier = len(node) >= 2 and \
                                  isinstance(node[1], nodes.classifier)
    def depart_definition_list_item(self, node):
        pass

    def visit_term(self, node):
        self.new_state(0)
    def depart_term(self, node):
        if not self._li_has_classifier:
            self.end_state(end=None)

    def visit_termsep(self, node):
        self.add_text(', ')
        raise nodes.SkipNode

    def visit_classifier(self, node):
        self.add_text(' : ')
    def depart_classifier(self, node):
        self.end_state(end=None)

    def visit_definition(self, node):
        self.new_state(self.indent)
    def depart_definition(self, node):
        self.end_state()

    def visit_field_list(self, node):
        # self.log_unknown("field_list", node)
        pass
    def depart_field_list(self, node):
        pass

    def visit_field(self, node):
        self.new_state(0)
    def depart_field(self, node):
        self.end_state(end=None)

    def visit_field_name(self, node):
        self.add_text(':')
    def depart_field_name(self, node):
        self.add_text(':')
        content = node.astext()
        self.add_text((16-len(content))*' ')

    def visit_field_body(self, node):
        self.new_state(self.indent)
    def depart_field_body(self, node):
        self.end_state()

    def visit_centered(self, node):
        pass
    def depart_centered(self, node):
        pass

    def visit_hlist(self, node):
        # self.log_unknown("hlist", node)
        pass
    def depart_hlist(self, node):
        pass

    def visit_hlistcol(self, node):
        # self.log_unknown("hlistcol", node)
        pass
    def depart_hlistcol(self, node):
        pass

    def _visit_admonition(self, node):
        self.new_state(0)
        if (node.tagname in self._base_admonitions):
            self.add_text('.. ' + node.tagname + ':: ')
        elif (node.tagname == 'admonition'):
            if node['classes'][0] in self._base_admonitions:
                self.add_text('.. ' + node['classes'][0] + ':: ')
            elif 'admonition' in node['classes'][0]:
                self.add_text('.. ' + 'admonition' + ':: ')
            else:
                self.log_warning("(%s) malformed admonition" % (node))
        else:
            self.log_warning("(%s) malformed admonition" % (node))
        if isinstance(node.children[0], nodes.title):
            for child in node.children[0]:
                child.walkabout(self)
                node.children.pop(0)
        self.end_state(wrap=False)
        self.new_state(self.indent)
        
    def _depart_admonition():
        def depart_admonition(self, node):
            self.end_state()
        return depart_admonition

    visit_admonition = _visit_admonition
    depart_admonition = _depart_admonition()
    visit_attention = _visit_admonition
    depart_attention = _depart_admonition()
    visit_caution = _visit_admonition
    depart_caution = _depart_admonition()
    visit_danger = _visit_admonition
    depart_danger = _depart_admonition()
    visit_error = _visit_admonition
    depart_error = _depart_admonition()
    visit_hint = _visit_admonition
    depart_hint = _depart_admonition()
    visit_important = _visit_admonition
    depart_important = _depart_admonition()
    visit_note = _visit_admonition
    depart_note = _depart_admonition()
    visit_tip = _visit_admonition
    depart_tip = _depart_admonition()
    visit_warning = _visit_admonition
    depart_warning = _depart_admonition()

    def visit_versionmodified(self, node):
        self.new_state(0)
    def depart_versionmodified(self, node):
        self.end_state()

    def visit_literal_block(self, node):
        is_code_block = False
        # Support for Sphinx < 2.0, which defines classes['code', 'language']
        if 'code' in node.get('classes', []):
            is_code_block = True
            if node.get('language', 'default') == 'default' and len(node['classes']) >= 2:
                node['language'] = node['classes'][1]
        # highlight_args is the only way to distinguish between :: and .. code:: in Sphinx 2 or higher.
        if node.get('highlight_args') != None:
            is_code_block = True
        if is_code_block:
            if node.get('language', 'default') == 'default':
                directive = ".. code::"
            else:
                directive = ".. code:: %s" % node['language']
            if node.get('linenos'):
                indent = self.indent * ' '
                directive += "%s%s:number-lines:" % (self.nl, indent)
        else:
            directive = "::"
        self.new_state(0)
        self.add_text(directive)
        self.end_state(wrap=False)
        self.new_state(self.indent)

    def depart_literal_block(self, node):
        self.end_state(wrap=False)

    def visit_doctest_block(self, node):
        self.new_state(0)
    def depart_doctest_block(self, node):
        self.end_state(wrap=False)

    def visit_line_block(self, node):
        self.new_state(0)
    def depart_line_block(self, node):
        self.end_state(wrap=False)

    def visit_line(self, node):
        # self.log_unknown("line", node)
        pass
    def depart_line(self, node):
        pass

    def visit_block_quote(self, node):
        self.new_state(self.indent)
    def depart_block_quote(self, node):
        self.end_state()

    def visit_compact_paragraph(self, node):
        self.visit_paragraph(node)
    def depart_compact_paragraph(self, node):
        self.depart_paragraph(node)

    def visit_container(self, node):
        self.new_state(0)
        if ('design_component' in node.attributes):
            self.add_text('.. ' + node.get('design_component') + ':: ')
            if isinstance(node.children[0], nodes.rubric):
                for child in node.children[0]:
                    child.walkabout(self)
            node.children.pop(0)
            self.end_state(wrap=False)
            self.new_state(self.indent)
        
    def depart_container(self, node):
        self.end_state(wrap=False)
        
    def visit_paragraph(self, node):
        if not isinstance(node.parent, nodes.Admonition) or \
               isinstance(node.parent, addnodes.seealso):
            self.new_state(0)
    def depart_paragraph(self, node):
        if not isinstance(node.parent, nodes.Admonition) or \
               isinstance(node.parent, addnodes.seealso):
            self.end_state()

    def visit_target(self, node):
        is_inline = node.parent.tagname in ('paragraph',)
        if is_inline or node.get('anonymous'):
            return
        refid = node.get('refid')
        refuri = node.get('refuri')
        if refid:
            self.new_state(0)
            if node.get('ids'):
                self.add_text(self.nl.join(
                    '.. _%s: %s_' % (id, refid) for id in node['ids']
                ))
            else:
                self.add_text('.. _'+node['refid']+':')
            self.end_state(wrap=False)
        raise nodes.SkipNode
    def depart_target(self, node):
        pass

    def visit_index(self, node):
        raise nodes.SkipNode

    def visit_substitution_definition(self, node):
        # try:
        #     next(node.findall(nodes.section, descend = False, ascend = True))
        # except StopIteration:
        #     self.add_text('|{}|'.format(node.get('names')[0]))
        #     return
        raise nodes.SkipNode

    def visit_pending_xref(self, node):
        pass
    def depart_pending_xref(self, node):
        pass

    def visit_reference(self, node):
        refname = node.get('name')
        refbody = node.astext()
        refuri = node.get('refuri')
        refid = node.get('refid')
        if not refname:
            refname = refbody
        if node.get('internal'):
            if 'refuri' in node: # internal
                if (isinstance(node.children[0], nodes.Inline) and node.children[0]['classes'] and 'doc' in node.children[0]['classes']):
                    for child in node.children:
                        child.walkabout(self)
                        self.add_text(' </{}>`'.format(refuri))
                elif (isinstance(node.children[0], nodes.Inline) and node.children[0]['classes'] and 'std-ref' in node.children[0]['classes']):
                    path = refuri.split('#')[0] # take only path
                    self.add_text(':ref:`{}:{}`'.format(path, refname))
                else:
                    refuri_split = refuri.split('#')
                    if len(refuri_split) == 1:
                         self.add_text(':doc:`{} </{}>`'.format(refname, refuri))
                    else:
                        self.add_text(':ref:`{}:{}`'.format(refuri_split[0], refname))
            else:
                assert 'refid' in node, \
                   'References must have "refuri" or "refid" attribute.'
                self.add_text(':ref:`{}`'.format(refid))
            raise nodes.SkipNode
        else:
            if refuri .startswith('mailto:'):
                return refbody
            return refuri

    def depart_reference(self, node):
        pass

    def visit_download_reference(self, node):
        if 'refuri' in node and 'reftype' in node and node['reftype'] == 'download':
            self.add_text(':download:`{}`'.format(node['refuri']))
        elif 'filename' in node:
            if (isinstance(node.children[0], nodes.Inline) and node.children[0]['classes'] and 'download' in node.children[0]['classes']):
                self.add_text(':download:`')
                for child in node.children:
                    child.walkabout(self)
                    self.add_text(' <{}>`'.format(node['reftarget']))
                raise nodes.SkipNode
        else:
            self.log_unknown("download_reference", node)
    def depart_download_reference(self, node):
        pass

    def visit_emphasis(self, node):
        self.add_text('*')
    def depart_emphasis(self, node):
        self.add_text('*')

    def visit_literal_emphasis(self, node):
        self.add_text('*')
    def depart_literal_emphasis(self, node):
        self.add_text('*')

    def visit_strong(self, node):
        self.add_text('**')
    def depart_strong(self, node):
        self.add_text('**')

    def visit_abbreviation(self, node):
        self.add_text('')
    def depart_abbreviation(self, node):
        if node.hasattr('explanation'):
            self.add_text(' (%s)' % node['explanation'])

    def visit_title_reference(self, node):
        # self.log_unknown("title_reference", node)
        self.add_text('*')
    def depart_title_reference(self, node):
        self.add_text('*')

    def visit_literal(self, node):
        if (node.parent.tagname == 'download_reference'):
            pass
        else:
            self.add_text('``')
    def depart_literal(self, node):
        if (node.parent.tagname == 'download_reference'):
            pass
        else:
            self.add_text('``')

    def visit_subscript(self, node):
        self.add_text(':sub:`')

    def depart_subscript(self, node):
        self.add_text('`')

    def visit_superscript(self, node):
        self.add_text(':sup:`')

    def depart_superscript(self, node):
        self.add_text('`')

    def visit_footnote_reference(self, node):
        self.add_text('[%s]' % node.astext())
        raise nodes.SkipNode

    def visit_citation_reference(self, node):
        self.add_text('[%s]' % node.astext())
        raise nodes.SkipNode

    def visit_math(self, node):
        self.add_text(":math:`")
        
    def depart_math(self, node):
        self.add_text("`")
        
    def visit_math_block(self, node):
        self.add_text(".. math::")
        self.new_state(self.indent)

    def depart_math_block(self, node):
        self.end_state(wrap=False)

    def visit_Text(self, node):
        self.add_text(node.astext())
    def depart_Text(self, node):
        pass

    def visit_generated(self, node):
        # self.log_unknown("generated", node)
        pass
    def depart_generated(self, node):
        pass

    def visit_inline(self, node):
        if (node.parent.tagname in ('reference,')):
            if node['classes'] and 'doc' in node['classes']:    # Check if :doc: must be written
                if (node.children[0]):                          # Check if link title
                    text = node.astext()                        # Get the title
                    node.clear()                                # Clear node body
                    node.append(nodes.Text(re.sub(r'[\*]', '', text)))  # replace by a Text node with cleaned-up content
                self.add_text(':%s:`' % node['classes'][0])
            else:
                self.log_warning('visit_inline - classes problem in %s' % node)
    def depart_inline(self, node):
        pass

    def visit_problematic(self, node):
        pass
    def depart_problematic(self, node):
        pass

    def visit_system_message(self, node):
        self.new_state(0)
        self.add_text('<SYSTEM MESSAGE: %s>' % node.astext())
        self.end_state()
        raise nodes.SkipNode

    def visit_comment(self, node):
        raise nodes.SkipNode

    def visit_meta(self, node):
        # only valid for HTML
        raise nodes.SkipNode

    def visit_raw(self, node):
        self.new_state(0)
        if 'text' in node.get('format', '').split():
            self.add_text(node.astext())
        if 'latex' in node.get('format', '').split():
            self.add_text('.. raw:: ' + "%s" % node['format'] + self.nl)
            self.new_state(self.indent)
            self.add_text(node.children[0])
            self.end_state(wrap=False)
        self.end_state()
        raise nodes.SkipNode

    def visit_docinfo(self, node):
        raise nodes.SkipNode

    def visit_fontawesome(self, node):
        if node.hasattr('classes') and node.hasattr('icon'):
            self.add_text(':' + node.get('classes')[0] + ':`' + node.get('icon') + '`')

    def depart_fontawesome(self, node):
        pass

    def visit_tabular_col_spec(self, node):
        if (node['spec']):
            self.add_text('.. tabularcolumns:: ' + "%s" % node['spec'])
    def depart_tabular_col_spec(self, node):
        pass

    def visit_ifconfig(self, node):
        self.new_state(0)
        self.add_text('.. ' + 'ifconfig' + ':: ' + node['expr'])
        self.end_state(wrap=False)
        self.new_state(self.indent)
    def depart_ifconfig(self, node):
        self.end_state()

    def visit_include(self, node):
        self.new_state(0)
        if 'text' in node.get('format', '').split():
            self.add_text(node.astext())
        self.end_state(wrap=False)
        raise nodes.SkipNode

    def depart_include(self, node):
        pass

    def unknown_visit(self, node):
        self.log_unknown(node.__class__.__name__, node)
        
    def unknown_departure(self, node):
        pass

    default_visit = unknown_visit
