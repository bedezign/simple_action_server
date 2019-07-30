import cgi
import logging
import os
import sys
import tempfile
from http import HTTPStatus
from http.server import __version__ as http_version, HTTPServer, SimpleHTTPRequestHandler  # noqa
# Use from..import for importlib as it needs to bootstrap some stuff before  "util" etc works, which import doesn't do
from importlib import import_module, util as importlib_util
from typing import AnyStr, Callable, Optional
from urllib.parse import parse_qs, ParseResult, urlparse

logger = logging.getLogger(__name__)


def action_identifier(verb: str, url: str) -> str:
    return verb.upper() + ' ' + url


class Action:

    def __init__(self, handler: Callable, origin: str = 'unknown', **kwargs):
        self.handler = handler
        self.origin = origin
        self._kwargs = kwargs

    def nextcall(self, **kwargs) -> 'Action':
        self._kwargs = kwargs
        return self

    def __call__(self, *args, **kwargs):
        final_kwargs = dict(**self._kwargs)
        final_kwargs.update(kwargs)
        return self.handler(*args, **final_kwargs)


class ActionRequestHandlerMeta(type):
    """
    Meta class with "class level" properties for the request handler below.
    Since every request results in a new instance, this is a way to provide properties for easy of use
    """

    def __init__(cls, *args, **kwargs):
        cls._action_sources = []
        cls._actions = {}
        cls._fallback = False
        super().__init__(*args, **kwargs)

    @property
    def action_sources(cls):
        """
        Action sources define modules where to look for matching functions.
        A source can be either an 'str', in which case we assume its a dot-notated (base) module, or a dict
        that contains a 'path' key (in which we assume you're specifying modules by a disk path.
        :return:
        """
        return cls._action_sources

    @property
    def actions(cls):
        """
        If you want to predefine actions, it can be done via this property.
        It's a dict that contains the URIs as key (without the QUERY part) and the matching function handler to call
        :return:
        """
        return cls._actions

    @action_sources.setter
    def action_sources(cls, sources: list):
        cls._action_sources = sources

    @actions.setter
    def actions(cls, actions: dict):
        cls._actions = actions

    def add_action(cls, verb: str, url: str, handler: Callable, origin: str = 'direct'):
        cls._actions[action_identifier(verb, url)] = Action(handler, origin)

    def remove_action(cls, verb: str, url: str, ):
        del cls._actions[action_identifier(verb, url)]

    def enable_fallback(cls, status: bool = True):
        """
        Fallback means that when a multi-level url is encountered, the resulting action can be linked "higher up"
        if no explicit match is found.
        For example: /test/test2 would normally map to function test_test2() (ignoring the prefix) but with
        fallback enabled, test() would also match if no specific match is found). /test/test2/test3 would also
        match test() in this situation.

        Can be handy but is potentially very dangerous if you're unaware so off by default.
        :param status:
        :return:
        """
        cls._fallback = status


class ActionRequestHandler(SimpleHTTPRequestHandler, metaclass=ActionRequestHandlerMeta):
    _action_modules = None
    server_version = 'SimpleActionHTTP/' + http_version

    def __init__(self, *args, **kwargs):
        self._file_path = None
        self._mime_type = None
        self._parsed_url = None
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        fields = cgi.FieldStorage(self.rfile, self.headers, environ={'REQUEST_METHOD': 'POST'})
        form = {}
        files = {}
        for f in fields.list:
            target = files if f.filename else form
            # Since HTTP allows for the same field to be present multiple times, add as list
            target.setdefault(f.name, []).append(f)

        self._dispatch(form, files)

    def do_HEAD(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def send_json(self, path=None, content=None):
        """
        Shortcut function to send a json file back to the client
        :param path: Physical path on the disk if this is a pre-existing file
        :param content: File content to use if not a file (str, dict, bytes)
        """
        if not isinstance(content, bytes):
            import json
            content = json.dumps(content) + '\n'
        if isinstance(content, str):
            content = content.encode()
        self.send_file(path, content, 'application/json')

    def send_file(self, path=None, content: bytes = None, type=None):
        if content:
            if not type:
                raise RuntimeError('Cannot determine mime type based on content, please specify')

            (fd, path) = tempfile.mkstemp()
            os.write(fd, content)

        # Temp-store the path & mime type so we can "dummy return" them
        self._file_path = path
        self._mime_type = type
        # Try to send the header already, this results in a file if successful
        f = self.send_head()

        if f:
            try:
                # Copy the file to the client
                self.copyfile(f, self.wfile)
            finally:
                f.close()

        if content:
            os.close(fd)
            os.unlink(path)

    def translate_path(self, path):
        """
        Override the base function and return the same path, since we're already working with those
        (we only use the send-file functionality, not the entire file hosting)
        :param path:
        :return:
        """
        return self._file_path

    def guess_type(self, path):
        """
        Override that supports pre-specified type
        :param path:
        :return:
        """
        return self._mime_type if self._mime_type else super().guess_type(path)

    def reply(self, http_code: int, response_message: str = None, content: AnyStr = None, content_type: AnyStr = None):
        self.send_response(http_code, response_message)

        body = None
        if content:
            body = content.encode('UTF-8', 'replace')
            # If we have content, make sure to add the correct headers
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header('Content-Length', str(len(content)))

        self.end_headers()

        if body:
            self.wfile.write(body)

    def success(self, response_message: str = None, content=None, content_type=None):
        """
        Shortcut function to report success
        """
        self.reply(HTTPStatus.OK, response_message, content, content_type)

    def handle_expect_100(self):
        (action, _) = self._find_action(self.path)
        if action.origin == 'error':
            self.send_404()
            return False

        return super().handle_expect_100()

    def _dispatch(self, form=None, files=None):
        action = self._find_action(self.path)

        if action and action.origin == 'error':
            logger.debug("Calling error handler for [%s %s]" % (self.command, self.parsed_url.path))

        if action:
            parameters = {
                "url": self.parsed_url
            }

            if self.parsed_url.query:
                parameters['query'] = parse_qs(self.parsed_url.query)

            if form:
                parameters['form'] = form

            if files:
                parameters['files'] = files

            action(self, **parameters)
        else:
            logger.error("No action for [%s %s]" % (self.command, self.parsed_url.path))
            self.send_404()

    def send_404(self):
        self.send_error(HTTPStatus.NOT_FOUND)

    @property
    def parsed_url(self) -> ParseResult:
        if not self._parsed_url:
            self._parsed_url = urlparse(self.path)
        return self._parsed_url

    def _find_action(self, path: str) -> Optional[Action]:
        action_name = self._request_identifier()

        prefixes = [self.command.lower(), 'any', '']

        # load the "top level" action modules
        self._load_action_modules()

        if action_name in self._actions:
            # We already found this
            return self._actions[action_name]

        for identifier in self._action_modules:

            parts = list(filter(None, urlparse(path).path.split('/')))
            (module, parts) = self._find_module(identifier, parts)

            # If we still have parts left, that will be (part of) the function name
            if module:
                if parts:
                    remainder = []
                    while parts:
                        # Function name is a combo of the remaining parts
                        function = '_'.join(parts)
                        # With optional <COMMAND>, "any" or no prefix
                        for prefix in prefixes:
                            try_function = '_'.join([prefix, function]).lstrip('_')
                            if hasattr(module, try_function):
                                return self._save_action(action_name, getattr(module, try_function), \
                                                         'direct' if not remainder else 'fallback')

                        if not self._fallback:
                            # No falling back to broader modules supported, abort
                            break

                        # Still here and we appear to have fallback enabled, pop the least significant part and try
                        # again for a broader action function
                        remainder.insert(0, parts.pop(-1))
                else:
                    method = self._find_catchall(module, self.command)
                    if method:
                        # Since this is a dedicated module, we still consider it a direct origin
                        return self._save_action(action_name, method, 'direct')

        # Still here, look through all of the modules again and find the first catch-all function that is either the
        # VERB/COMMAND or "any"
        for _, module in self._action_modules.items():
            module = module[0]
            method = self._find_catchall(module, self.command)
            if method:
                return self._save_action(action_name, method, 'catchall')

        # Do we have 404 actions?
        for prefix in [self.command, 'ANY', '']:
            name = ' '.join([prefix, '404']).strip()
            if name in self._actions:
                return Action(self._actions[name], 'error')

        # nothing found, use default functionality
        return None

    def _request_identifier(self) -> str:
        return action_identifier(self.command, self.parsed_url.path)

    def _save_action(self, action_name, method, origin):
        logger.debug(
            'Action "%s" was mapped to "%s.%s" [%s]' % (action_name, method.__module__, method.__name__, origin))

        self._actions[action_name] = Action(method, origin, original_url=self.parsed_url)
        return self._actions[action_name]

    def _find_module(self, identifier: str, parts: list):
        """
        Given the module identified by "identifier", try to enumerate into its submodules as deep as possible using
        the parts list and return the found module and the remaining parts.
        :param identifier:
        :param parts:
        :return:
        """

        parts = list(parts)
        (module, origin) = self._action_modules[identifier]
        if origin == 'module':
            while parts:
                part = parts.pop(0)
                try:
                    name = module.__name__ + '.' + part
                    # Always load starting from the base module so relative imports work
                    spec = importlib_util.find_spec(name)  # noqa
                    if not spec:
                        parts.insert(0, part)
                        break
                except (ModuleNotFoundError, ValueError):
                    # Put part back in list
                    parts.insert(0, part)
                    break

                try:
                    module = spec.loader.load_module()
                except Exception as e:
                    logger.warning('Unable to load module "%s" : Coding error? Exception was: ' % name + repr(e))
                    parts.insert(0, part)
                    break

        elif origin == 'path':
            # See how "low" we can go directory-wise first
            while parts:
                part = parts.pop(0)
                try_dir = os.path.join(base, part)
                if not os.path.isdir(try_dir):
                    parts.insert(0, part)
                    break
                base = try_dir

            # now that we know in which directory we'll need to find the logic:
            sys.path.append(os.path.abspath(base))
            file = parts.pop(0)
            module = import_module(file)

        return module, parts

    def _find_catchall(self, module, command):
        methods = [command.lower(), 'any']
        for method in methods:
            if hasattr(module, method):
                return getattr(module, method)

    @classmethod
    def _load_action_modules(cls):
        """
        Given a list of action sources, load the top level modules for each
        :return:
        """
        if cls._action_modules is not None:
            return

        cls._action_modules = {}
        for item in cls.action_sources:
            name = None
            path = None
            if isinstance(item, dict):
                if 'module' in item:
                    name = item['module']
                elif 'package' in item:
                    name = item['package']
                elif 'path' in item:
                    path = item['path']
            elif isinstance(item, str):
                # String = module/package identifier
                name = item

            try:
                if name:
                    spec = importlib_util.find_spec(item)  # noqa
                    if spec:
                        cls._action_modules[name] = (spec.loader.load_module(), 'module')
                elif path:
                    # Load from path physical path...
                    abs_path = os.path.abspath(path)
                    sys.path.append(abs_path)
                    cls._action_modules[path] = (import_module(os.path.basename(abs_path)), 'path')

            except ModuleNotFoundError:
                pass


def serve(host_name: str = '', host_port: int = 8080, actions: dict = None, action_sources: list = None):
    """
    Start a simple action server on host_name/host_port, optionally pre-specifying actions
    :param host_name: listen on this IP (empty = all interfaces)
    :param host_port: port to use (defaults to 8080)
    :param actions: dict of actions to method. Action identifier is VERB + absolute URI (eg 'POST /ping").
    :param action_sources: List of strings (if you are specifying module identifiers) where the action methods can be
                           looked for.
    :return:
    """

    if actions:
        ActionRequestHandler.actions = actions

    action_sources = action_sources if action_sources else [] + ['.'.join(__name__.split('.')[:-1]) + '.actions']
    ActionRequestHandler.action_sources = action_sources

    server = HTTPServer((host_name, host_port), ActionRequestHandler)
    logger.debug("START - %s:%s" % (host_name, host_port))

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    server.server_close()
    logger.debug("STOP - %s:%s" % (host_name, host_port))
