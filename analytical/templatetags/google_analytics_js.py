"""
Google Analytics template tags and filters, using the new analytics.js library.
"""

from __future__ import absolute_import

import decimal
import re
from django.conf import settings
from django.template import Library, Node, TemplateSyntaxError

from analytical.utils import (
    AnalyticalException,
    disable_html,
    get_domain,
    get_identity,
    get_required_setting,
    is_internal_ip,
)

TRACK_SINGLE_DOMAIN = 1
TRACK_MULTIPLE_SUBDOMAINS = 2
TRACK_MULTIPLE_DOMAINS = 3

PROPERTY_ID_RE = re.compile(r'^UA-\d+-\d+$')
SETUP_CODE = """
<script>
(function(i,s,o,g,r,a,m){{i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){{
(i[r].q=i[r].q||[]).push(arguments)}},i[r].l=1*new Date();a=s.createElement(o),
m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
}})(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

ga('create', '{property_id}', 'auto', {create_fields});
{commands}ga('send', 'pageview');
</script>
"""
REQUIRE_DISPLAY_FEATURES = "ga('require', 'displayfeatures');\n"
CUSTOM_VAR_CODE = "ga('set', '{name}', {value});\n"
ANONYMIZE_IP_CODE = "ga('set', 'anonymizeIp', true);\n"

register = Library()


@register.tag
def google_analytics_js(parser, token):
    """
    Google Analytics tracking template tag.

    Renders Javascript code to track page visits.  You must supply
    your website property ID (as a string) in the
    ``GOOGLE_ANALYTICS_JS_PROPERTY_ID`` setting.
    """
    is_required = False
    bits = token.split_contents()
    if len(bits) > 1:
        # check for "is_required" argument being set
        if bits[1] == 'is_required':
            is_required = True
        else:
            raise TemplateSyntaxError("'%s' takes no arguments" % bits[0])
    return GoogleAnalyticsJsNode(is_required)


class GoogleAnalyticsJsNode(Node):
    def __init__(self, is_required):
        if is_required:
            self.property_id = get_required_setting(
                'GOOGLE_ANALYTICS_JS_PROPERTY_ID', PROPERTY_ID_RE,
                "must be a string looking like 'UA-XXXXXX-Y'")
        else:
            # all good, just see if it's defined but don't complain if not
            self.property_id = getattr(settings, 'GOOGLE_ANALYTICS_JS_PROPERTY_ID', None)

    def render(self, context):
        # do nothing if no GA property ID provided
        if not self.property_id:
            return '<!-- Google Analytics disabled due to no Property_ID -->'

        import json
        create_fields = self._get_domain_fields(context)
        create_fields.update(self._get_other_create_fields(context))
        commands = self._get_custom_var_commands(context)
        commands.extend(self._get_other_commands(context))
        display_features = getattr(settings, 'GOOGLE_ANALYTICS_DISPLAY_ADVERTISING', False)
        if display_features:
            commands.insert(0, REQUIRE_DISPLAY_FEATURES)

        html = SETUP_CODE.format(
            property_id=self.property_id,
            create_fields=json.dumps(create_fields),
            commands="".join(commands),
        )
        if is_internal_ip(context, 'GOOGLE_ANALYTICS'):
            html = disable_html(html, 'Google Analytics')
        return html

    def _get_domain_fields(self, context):
        domain_fields = {}
        tracking_type = getattr(settings, 'GOOGLE_ANALYTICS_TRACKING_STYLE', TRACK_SINGLE_DOMAIN)
        if tracking_type == TRACK_SINGLE_DOMAIN:
            pass
        else:
            domain = get_domain(context, 'google_analytics')
            if domain is None:
                raise AnalyticalException(
                    "tracking multiple domains with Google Analytics requires a domain name")
            domain_fields['legacyCookieDomain'] = domain
            if tracking_type == TRACK_MULTIPLE_DOMAINS:
                domain_fields['allowLinker'] = True
        return domain_fields

    def _get_other_create_fields(self, context):
        other_fields = {}

        user_identity = get_identity(context, 'google_analytics', self._identify)
        if user_identity is not None:
            other_fields['userId'] = str(user_identity)
            
        site_speed_sample_rate = getattr(settings, 'GOOGLE_ANALYTICS_SITE_SPEED_SAMPLE_RATE', False)
        if site_speed_sample_rate is not False:
            value = int(decimal.Decimal(site_speed_sample_rate))
            if not 0 <= value <= 100:
                raise AnalyticalException(
                    "'GOOGLE_ANALYTICS_SITE_SPEED_SAMPLE_RATE' must be >= 0 and <= 100")
            other_fields['siteSpeedSampleRate'] = value

        sample_rate = getattr(settings, 'GOOGLE_ANALYTICS_SAMPLE_RATE', False)
        if sample_rate is not False:
            value = int(decimal.Decimal(sample_rate))
            if not 0 <= value <= 100:
                raise AnalyticalException("'GOOGLE_ANALYTICS_SAMPLE_RATE' must be >= 0 and <= 100")
            other_fields['sampleRate'] = value

        cookie_expires = getattr(settings, 'GOOGLE_ANALYTICS_COOKIE_EXPIRATION', False)
        if cookie_expires is not False:
            value = int(decimal.Decimal(cookie_expires))
            if value < 0:
                raise AnalyticalException("'GOOGLE_ANALYTICS_COOKIE_EXPIRATION' must be >= 0")
            other_fields['cookieExpires'] = value

        return other_fields

    def _identify(self, user):
        return getattr(user, 'id', None)

    def _get_custom_var_commands(self, context):
        values = (
            context.get('google_analytics_var%s' % i) for i in range(1, 6)
        )
        params = [(i, v) for i, v in enumerate(values, 1) if v is not None]
        commands = []
        for _, var in params:
            name = var[0]
            value = var[1]
            try:
                float(value)
            except ValueError:
                value = "'{}'".format(value)
            commands.append(CUSTOM_VAR_CODE.format(
                name=name,
                value=value,
            ))
        return commands

    def _get_other_commands(self, context):
        commands = []

        if getattr(settings, 'GOOGLE_ANALYTICS_ANONYMIZE_IP', False):
            commands.append(ANONYMIZE_IP_CODE)

        return commands


def contribute_to_analytical(add_node):
    GoogleAnalyticsJsNode(True)  # ensure properly configured
    add_node('head_bottom', GoogleAnalyticsJsNode)
