"""
Tests for third_party_auth decorators.
"""
import json
import unittest
import datetime

import ddt
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory
from mock import MagicMock

from third_party_auth.decorators import xframe_allow_whitelisted, allow_frame_from_whitelisted_url, tpa_hint_ends_existing_session
from third_party_auth.tests.testutil import TestCase
from six.moves.urllib.parse import urlencode

SCORM_CLOUD_URL = 'https://cloud.scorm.com'


def mock_view(_request):
    """ A test view for testing purposes. """
    return HttpResponse()


@tpa_hint_ends_existing_session
def mock_hinted_view(request):
    """
    Another test view for testing purposes.
    """
    return JsonResponse({"tpa_hint": request.GET.get('tpa_hint')})


# remove this decorator once third_party_auth is enabled in CMS
@unittest.skipIf(
    'third_party_auth' not in settings.INSTALLED_APPS,
    'third_party_auth is not currently installed in CMS'
)
@ddt.ddt
class TestXFrameWhitelistDecorator(TestCase):
    """ Test the xframe_allow_whitelisted decorator. """

    def setUp(self):
        super(TestXFrameWhitelistDecorator, self).setUp()
        self.configure_lti_provider(name='Test', lti_hostname='localhost', lti_consumer_key='test_key', enabled=True)
        self.factory = RequestFactory()

    def construct_request(self, referer):
        """ Add the given referer to a request and then return it. """
        request = self.factory.get('/login')
        request.META['HTTP_REFERER'] = referer
        return request

    @ddt.unpack
    @ddt.data(
        ('http://localhost:8000/login', 'ALLOW'),
        ('http://not-a-real-domain.com/login', 'DENY'),
        (None, 'DENY')
    )
    def test_x_frame_options(self, url, expected_result):
        request = self.construct_request(url)

        response = xframe_allow_whitelisted(mock_view)(request)

        self.assertEqual(response['X-Frame-Options'], expected_result)

    @ddt.data('http://localhost/login', 'http://not-a-real-domain.com', None)
    def test_feature_flag_off(self, url):
        with self.settings(FEATURES={'ENABLE_THIRD_PARTY_AUTH': False}):
            request = self.construct_request(url)
            response = xframe_allow_whitelisted(mock_view)(request)
            self.assertEqual(response['X-Frame-Options'], 'DENY')


@unittest.skipIf(
    'third_party_auth' not in settings.INSTALLED_APPS,
    'third_party_auth is not currently installed in CMS'
)
@ddt.ddt
class TestTpaHintSessionEndingDecorator(TestCase):
    """
    In cases where users may be sharing computers, we want to ensure
    that a hinted link (has a tpa_hint query parameter) from an external site
    will always force the user to login again with SSO, even if the user is already
    logged in. (For SSO providers that enable this option.)

    This aims to prevent a situation where user 1 forgets to logout,
    then user 2 logs in to the external site and takes a link to the
    Open edX instance, but gets user 1's session.
    """

    url = '/protected_view'

    def setUp(self):
        super(TestTpaHintSessionEndingDecorator, self).setUp()
        self.enable_saml()
        self.factory = RequestFactory()

    def get_user_mock(self, authenticated=False):
        user = MagicMock()
        user.is_authenticated.return_value = authenticated
        return user

    def get_request_mock(self, authenticated=False, hinted=False, done=False):
        user = self.get_user_mock(authenticated)
        params = {}
        if hinted:
            params['tpa_hint'] = 'saml-realprovider'
        if done:
            params['session_cleared'] = 'yes'
        url = '{}?{}'.format(self.url, urlencode(params))
        request = self.factory.get(url)
        request.user = user
        return request

    def create_provider(self, protected=False):
        self.configure_saml_provider(
            enabled=True,
            name="Fancy real provider",
            idp_slug="realprovider",
            backend_name="tpa-saml",
            drop_existing_session=protected,
        )

    @ddt.unpack
    @ddt.data(
        (True, True, False, False, False),
        (True, True, True, False, True),
        (True, True, True, True, False),
        (True, True, False, True, False),
        (False, True, True, False, False),
        (True, False, True, False, False),
    )
    def test_redirect_when_logged_in_with_hint(self, protected, authenticated, hinted, done, redirects):
        self.create_provider(protected)
        request = self.get_request_mock(authenticated, hinted, done)
        response = mock_hinted_view(request)
        if redirects:
            self.assertRedirects(
                response,
                '/logout?redirect_url=%2Fprotected_view%3Ftpa_'
                'hint%3Dsaml-realprovider%26session_cleared%3Dyes',
                fetch_redirect_response=False,
            )
        else:
            self.assertEqual(json.loads(response.content)['tpa_hint'], ('saml-realprovider' if hinted else None))


# remove this decorator once third_party_auth is enabled in CMS
@unittest.skipIf(
    'third_party_auth' not in settings.INSTALLED_APPS,
    'third_party_auth is not currently installed in CMS'
)
@ddt.ddt
class TestXFrameWhitelistDecoratorForSAML(TestCase):
    """ Test the allow_frame_from_whitelisted_url decorator. """

    def setUp(self):
        super(TestXFrameWhitelistDecoratorForSAML, self).setUp()
        self.configure_saml_provider_data(
            entity_id='https://idp.testshib.org/idp/shibboleth',
            sso_url='https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO/',
            public_key='testkey',
            fetched_at=datetime.datetime.now()
        )
        self.factory = RequestFactory()

    def construct_request(self, referer):
        """ Add the given referer to a request and then return it. """
        request = self.factory.get('/auth/custom_auth_entry')
        request.META['HTTP_REFERER'] = referer
        return request

    @ddt.unpack
    @ddt.data(
        (
            'https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO/?param1=1&param2=',
            {
                'X-Frame-Options': 'ALLOW-FROM %s' % SCORM_CLOUD_URL,
                'Content-Security-Policy': "frame-ancestors %s" % SCORM_CLOUD_URL,

            }
        ),
        (
            'https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO?param1=1&param2=',
            {
                'X-Frame-Options': 'ALLOW-FROM %s' % SCORM_CLOUD_URL,
                'Content-Security-Policy': "frame-ancestors %s" % SCORM_CLOUD_URL,

            }
        ),
        (
            'http://not-a-real-domain.com/SSO',
            {
                'X-Frame-Options': 'DENY',
                'Content-Security-Policy': "frame-ancestors 'none'",

            }
        ),
        (
            None,
            {
                'X-Frame-Options': 'DENY',
                'Content-Security-Policy': "frame-ancestors 'none'",

            }
        )
    )
    def test_x_frame_options(self, url, expected_headers):
        with self.settings(THIRD_PARTY_AUTH_FRAME_ALLOWED_FROM_URL=[SCORM_CLOUD_URL]):
            request = self.construct_request(url)
            response = allow_frame_from_whitelisted_url(mock_view)(request)
            for header, value in expected_headers.items():
                self.assertEqual(response[header], value)

    @ddt.data('https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO', 'http://not-a-real-domain.com/SSO', None)
    def test_feature_flag_off(self, url):
        with self.settings(FEATURES={'ENABLE_THIRD_PARTY_AUTH': False}):
            request = self.construct_request(url)
            response = allow_frame_from_whitelisted_url(mock_view)(request)
            self.assertEqual(response['X-Frame-Options'], 'DENY')
            self.assertEqual(response['Content-Security-Policy'], "frame-ancestors 'none'")
