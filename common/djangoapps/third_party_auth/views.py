"""
Extra views required for SSO
"""


from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseNotFound, HttpResponseServerError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from social_core.utils import setting_name
from social_django.utils import load_backend, load_strategy, psa
from social_django.views import complete

import third_party_auth
from student.helpers import get_next_url_for_login_page
from student.models import UserProfile
from student.views import compose_and_send_activation_email
from third_party_auth import pipeline, provider

from .models import SAMLConfiguration, SAMLProviderConfig
from .decorators import allow_frame_from_whitelisted_url

URL_NAMESPACE = getattr(settings, setting_name('URL_NAMESPACE'), None) or 'social'


def inactive_user_view(request):
    """
    A newly or recently registered user has completed the social auth pipeline.
    Their account is not yet activated, but we let them login since the third party auth
    provider is trusted to vouch for them. See details in pipeline.py.

    The reason this view exists is that if we don't define this as the
    SOCIAL_AUTH_INACTIVE_USER_URL, inactive users will get sent to LOGIN_ERROR_URL, which we
    don't want.

    If the third_party_provider.skip_email_verification is set then the user is activated
    and verification email is not sent
    """
    # 'next' may be set to '/account/finish_auth/.../' if this user needs to be auto-enrolled
    # in a course. Otherwise, just redirect them to the dashboard, which displays a message
    # about activating their account.
    user = request.user
    profile = UserProfile.objects.get(user=user)
    activated = user.is_active
    # If the user is registering via 3rd party auth, track which provider they use
    if third_party_auth.is_enabled() and pipeline.running(request):
        running_pipeline = pipeline.get(request)
        third_party_provider = provider.Registry.get_from_pipeline(running_pipeline)
        if third_party_provider.skip_email_verification and not activated:
            user.is_active = True
            user.save()
            activated = True
    if not activated:
        compose_and_send_activation_email(user, profile)

    return redirect(request.GET.get('next', 'dashboard'))


def saml_metadata_view(request):
    """
    Get the Service Provider metadata for this edx-platform instance.
    You must send this XML to any Shibboleth Identity Provider that you wish to use.
    """
    idp_slug = request.GET.get('tpa_hint', None)
    saml_config = 'default'
    if idp_slug:
        idp = SAMLProviderConfig.current(idp_slug)
        if idp.saml_configuration:
            saml_config = idp.saml_configuration.slug
    if not SAMLConfiguration.is_enabled(request.site, saml_config):
        raise Http404
    complete_url = reverse('social:complete', args=("tpa-saml", ))
    if settings.APPEND_SLASH and not complete_url.endswith('/'):
        complete_url = complete_url + '/'  # Required for consistency
    saml_backend = load_backend(load_strategy(request), "tpa-saml", redirect_uri=complete_url)
    metadata, errors = saml_backend.generate_metadata_xml(idp_slug)

    if not errors:
        return HttpResponse(content=metadata, content_type='text/xml')
    return HttpResponseServerError(content=', '.join(errors))


@csrf_exempt
@psa('{0}:complete'.format(URL_NAMESPACE))
def lti_login_and_complete_view(request, backend, *args, **kwargs):
    """This is a combination login/complete due to LTI being a one step login"""

    if request.method != 'POST':
        return HttpResponseNotAllowed('POST')

    request.backend.start()
    return complete(request, backend, *args, **kwargs)


@allow_frame_from_whitelisted_url
def post_to_custom_auth_form(request):
    """
    Redirect to a custom login/register page.

    Since we can't do a redirect-to-POST, this view is used to pass SSO data from
    the third_party_auth pipeline to a custom login/register form (possibly on another server).
    """
    pipeline_data = request.session.pop('tpa_custom_auth_entry_data', None)
    if not pipeline_data:
        raise Http404
    # Verify the format of pipeline_data:
    try:
        data = pipeline_data['data'].decode('utf-8')
        hmac = pipeline_data['hmac'].decode('utf-8')
    except AttributeError:
        data = pipeline_data['data']
        hmac = pipeline_data['hmac']

    data = {
        'post_url': pipeline_data['post_url'],
        # data: The provider info and user's name, email, etc. as base64 encoded JSON
        # It's base64 encoded because it's signed cryptographically and we don't want whitespace
        # or ordering issues affecting the hash/signature.
        'data': data,
        # The cryptographic hash of user_data:
        'hmac': hmac,
    }
    return render(request, 'third_party_auth/post_custom_auth_entry.html', data)


class IdPRedirectView(View):
    """
    Redirect to an IdP's login page if the IdP exists; otherwise, return a 404.

    Example usage:

        GET auth/idp_redirect/saml-default

    """
    def get(self, request, *args, **kwargs):
        """
        Return either a redirect to the login page of an identity provider that
        corresponds to the provider_slug keyword argument or a 404 if the
        provider_slug does not correspond to an identity provider.

        Args:
            request (HttpRequest)

        Keyword Args:
            provider_slug (str): a slug corresponding to a configured identity provider

        Returns:
            HttpResponse: 302 to a provider's login url if the provider_slug kwarg matches an identity provider
            HttpResponse: 404 if the provider_slug kwarg does not match an identity provider
        """
        # this gets the url to redirect to after login/registration/third_party_auth
        # it also handles checking the safety of the redirect url (next query parameter)
        # it checks against settings.LOGIN_REDIRECT_WHITELIST, so be sure to add the url
        # to this setting
        next_destination_url = get_next_url_for_login_page(request)

        try:
            url = pipeline.get_login_url(kwargs['provider_slug'], pipeline.AUTH_ENTRY_LOGIN, next_destination_url)
            return redirect(url)
        except ValueError:
            return HttpResponseNotFound()
