import logging
from django.contrib import messages
from django.shortcuts import redirect
from django.http import Http404
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

class GlobalExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Ignore 404s and Permission Denied so they are handled natively
        if isinstance(exception, (Http404, PermissionDenied)):
            return None

        # Log the exception
        logger.error(f"Unhandled Exception in request {request.path}: {exception}", exc_info=True)

        # Skip JSON/AJAX requests as they should return JSON responses, not redirects
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
            from django.http import JsonResponse
            return JsonResponse({'error': 'সিস্টেমে একটি অপ্রত্যাশিত ত্রুটি হয়েছে। দয়া করে আবার চেষ্টা করুন।'}, status=500)

        # Add error message
        messages.error(request, "সিস্টেমে একটি অপ্রত্যাশিত ত্রুটি হয়েছে। দয়া করে আবার চেষ্টা করুন।")
        
        # Redirect gracefully
        referer = request.META.get('HTTP_REFERER')
        if referer and request.build_absolute_uri() != referer:
            return redirect(referer)
        
        return redirect('/')
