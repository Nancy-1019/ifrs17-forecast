"""Django context processors for IFRS17 system."""
from django.conf import settings

def system_config(request):
    return {
        'SYSTEM_VERSION': settings.SYSTEM_VERSION,
        'BUILD_DATE': settings.BUILD_DATE,
    }
