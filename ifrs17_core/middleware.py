"""Django middleware for IFRS17 system."""
from django.conf import settings


class NoCacheHTMLMiddleware:
    """对 HTML 响应添加 no-cache 头，防止浏览器缓存页面。

    静态文件（JS/CSS）通过 ?v=版本号 进行缓存控制，
    而 HTML 页面必须每次都从服务器获取最新版本，
    这样浏览器才能看到最新的 ?v=xxx 引用。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        content_type = response.get('Content-Type', '')
        if 'text/html' in content_type:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
