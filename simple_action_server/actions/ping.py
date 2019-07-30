from ..main import ActionRequestHandler as RequestHandler


#
# The name "any" basically means that this function will get a call for any of the verbs (GET/POST/HEAD at this moment)
# Since the action is part of the module "ping" this means that everything "/ping"
# will be redirected to this function.
def any(request: RequestHandler,
        url: 'urllib.parse.ParseResult' = None,
        query: dict = None,
        form: 'Dict[List[cgi.FieldStorage]]' = None,
        files: 'Dict[List[cgi.FieldStorage]]' = None,
        original_url: 'urllib.parse.ParseResult' = None,
        ):
    """
    Action Handler function as an example. This responds with an 200-OK when a user does /ping

    :param request: The Handler that is being used to store the current request
    :param url: The parsed url for which this handler was called
    :param query: If any, the parsed query string
    :param form: Any posted form fields as a dict keyed by the field name with a list of FieldStorage instances as value
    :param files: Any posted files, "
    """
    request.success('Pong', content="Blah")
