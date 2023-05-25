from sphinx.directives.other import Include
from ..restbuilder import include

class Include(Include):
    """ Override the default Sphinx Include class by creating a new include node that insert raw content """

    def run(self):
        current_line = self.lineno - self.state_machine.input_offset - 1
        if ('rst_prolog' in self.state_machine.input_lines.items[current_line][0]):
            return []       # Skip includes from rst_prolog
        attributes = {'format': 'text'}
        node = include('', self.block_text, classes=self.options.get('class', []), **attributes)
        (node.source,
         node.line) = self.state_machine.get_source_and_line(self.lineno)
        return [node]

