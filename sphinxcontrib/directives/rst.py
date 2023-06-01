from sphinx.directives.other import Include
from ..restbuilder import include

class Include(Include):
    """ Override the default Sphinx Include class by creating a new include node that insert raw content """

    def run(self):
        if (self.env.app.builder.name == 'rst'):
            current_line = self.lineno - self.state_machine.input_offset - 1
            if ('rst_prolog' in self.state_machine.input_lines.items[current_line][0]):
                return super().run()       # Skip includes from rst_prolog
            attributes = {'format': 'text'}
            node = include('', self.block_text, classes=self.options.get('class', []), **attributes)
            (node.source,
             node.line) = self.state_machine.get_source_and_line(self.lineno)
            return [node]
        else:
            return super().run()

def set_ifconfig_nodes_status(app):
    if (app.builder.name == 'rst'):
        # 'process_ifconfig_nodes' listener only removed for 'rst' builder
        for listeners in app.events.listeners.values():
            for listener in listeners[:]:
                if (listener.handler.__name__ == 'process_ifconfig_nodes'):
                    listeners.remove(listener)
