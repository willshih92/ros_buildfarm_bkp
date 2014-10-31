from em import Error
from em import Interpreter
from io import StringIO
import os
import sys
from xml.sax.saxutils import escape

template_basepath = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'templates'))


template_hook = None


def expand_template(template_name, data, options=None):
    global template_hook
    output = StringIO()
    try:
        interpreter = Interpreter(output=output, options=options)
        template_path = os.path.join(template_basepath, template_name)
        # create copy before manipulating
        data = dict(data)
        data['ESCAPE'] = _escape_value
        data['SNIPPET'] = _expand_snippet
        interpreter.file(open(template_path), locals=data)
        value = output.getvalue()
        if template_hook:
            template_hook(template_name, data, value)
        return value
    except Exception as e:
        print("%s processing template '%s'" %
              (e.__class__.__name__, template_name), file=sys.stderr)
        raise
    finally:
        interpreter.shutdown()


def _escape_value(value):
    if isinstance(value, list):
        value = [_escape_value(v) for v in value]
    elif isinstance(value, set):
        value = set([_escape_value(v) for v in value])
    elif isinstance(value, str):
        value = escape(value)
    return value


def _expand_snippet(snippet_name, **kwargs):
    template_name = 'snippet/%s.xml.em' % snippet_name
    try:
        value = expand_template(template_name, kwargs)
        return value
    except Error as e:
        print("%s in snippet '%s': %s" %
              (e.__class__.__name__, snippet_name, str(e)), file=sys.stderr)
        sys.exit(1)
