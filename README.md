# Simple Action Server

```text
Feed me modules or functions and I'll serve you right!
``` 

This is a proof of concept for a webserver that I wanted to be able to use with minimal setup.
Its routing is based on the layout of your modules and function names (optionally you can link directly to functions if you want).
 
To start it, you call the `serve()`-function (from `main`) and you give it a `dict` of `<identifier>: <callable>` entries,
and/or a number of module identifiers that are explored automatically.

It is based on the `http.server.SimpleHTTPRequestHandler` for its file functionality but overrides most of it.

## Action

And action is what gets called when a specific url is requested.
The action receives a number of pre-digested variables to allow it to do its thing quicker.

The definition is as follows:
```python
import simple_action_server.main

def handle(request: simple_action_server.main.ActionRequestHandler,
            url: 'urllib.parse.ParseResult' = None,
            query: dict = None,
            form: 'Dict[List[cgi.FieldStorage]]' = None,
            files: 'Dict[List[cgi.FieldStorage]]' = None,
            original_url: 'urllib.parse.ParseResult' = None,
        ):
    pass
```

* `request`: The request instance we're currently processing. Provides you with a number of helper functions to reply.
* `url`: The url on which we've received the request. This is the URL without the query part. In case you want to link more than one url to a single function
* `query`: (optional) If the URL had a query part, this contains a parsed `dict`.
* `form`: (optional) If a form was posted, this contains the relevant FieldStorage entries
* `files`: (optional) Like form, but uploaded files only
* `original_url`: The full parse result of the URL in case you need it 

For `query`, `form` and `files`, the entries contain "a list of values". `cgi.FieldStorage` does
this automatically and since it makes sense (each field can be specified multiple times) it was
also implemented in the `query`-`dict` for consistency.

This simply means that (in most cases) you do `query['field-name'][0]` to get to the value.


## actions-list

If you want to link URLs to functions, use the `actions` parameter as described above.
The `action_identifier`-function helps you compose the correct identifier:

```python
from simple_action_server.main import serve as serve, action_identifier as identifier

def pong(request, **_):
    request.success('Pong', content="Pong") 

serve(actions = {
    identifier('get', '/ping'): pong
})
```

This starts a webserver that responds to a `/ping`-GET request with Pong (both as a status message and as content)  

Note that like this, the name of the handler is of no consequence, it's only the function it
points at we require.

## action_sources-list

If it's auto detection you want, this is the way to go. Via this parameter you can specify one or more modules
that contain action-handlers. What you specify will be looked at as the root and the requesting URL will be
used to determine the final function handler.

If you use a simple string, it is assumed to be a root module identifier (eg `simpple_action_server.actions`).
Alternatively it can be a `dict`. For this we support the keys "module" or "package" (same behavior as a string) or
"path" indicating a source path should be used.

### Mapping onto actions

To determine what function to use, we split the URL in parts and try to load a sub-module for every part. 
As long as this succeeds we keep trying.

If we no more modules are found there are a couple possibilities:
1. There's one part left: We'll try that on as a function. What we look for is "<verb>_<name>" initially (eg "`get_ping`"),
   If no such function exists within the module, `any_<name>` is tried. Lastly, plain `<name>`. The first match wins.
2. There are NO parts left: (aka "we have a module with the exact url parts name"): We're trying `<verb>` and `any` as functions.    
3. There are multiple parts left: The parts are combined with underscore and the same logic applies as for one part.
    For example (`/tools/ping`) will be looked for as `<verb>_tools_ping`, `any_tools_ping` and just `tools_ping`.
    If none of these matches, there is a "fallback"-mode (that is disabled by default), where it will also try a broader 
    approach. In the case of the example, `<verb>_tools`, `any_tools` and just plain `tools` would be tried if this is enabled.

If none-of these work out, the next `action_source` is tried.

If we went through all `action_source`s, and no match was found, we'll repeat the story and try to locate "catch all"-functions
for the modules. Eg `get` or `any`. 

When that yields nothing we've failed and will try to locate an error method called `404` according to the same rules (`<verb|any>_404` since simply 404 wont work) 

If there's no user error function we'll take care of that ourselves.

## Responding

The handler you get has a couple handy functions to speed up things:

* `reply`: The full function allowing you to specify the http result, response message (eg the "OK" in "`HTTP 200 OK`") and the content in one go
* `success`: As above but takes care of the status code for you
* `send_json`: Reply with json content, either from a string (`content=`) or a path (`path=`). This does not send a status (you can send a json in error as well), use `send_response` yourself.
* `send_file`: Like above but for any file (content type can be specified). Same what the status code is concerned.

And obviously any function available in `SimpleHTTPRequestHandler`