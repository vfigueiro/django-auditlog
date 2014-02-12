from threading import local


_thread_locals = local()


def get_current_request():
    """Return current request from threadlocals"""
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    """Return current user from threadlocals if authenticated"""
    request = get_current_request()
    if request:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated():
            return user
    return None


def get_current_ip():
    """Return current ip address from threadlocals"""
    request = get_current_request()
    if request:
        if 'HTTP_X_FORWARDED_FOR' in request.META:
            ip = request.META['HTTP_X_FORWARDED_FOR']
        elif 'Client-IP' in request.META:
            ip = request.META['Client-IP']
        else:
            ip = request.META['REMOTE_ADDR']
        return ip.split(',')[0]
    return None


def get_current_path():
    """Return the path of the request from threadlocals"""
    request = get_current_request()
    if request:
        return request.get_full_path()[:255]
    return ''



class AuditlogMiddleware(object):
    """A middleware class that adds the request to threadlocals"""

    def process_request(self, request):
        _thread_locals.request = request