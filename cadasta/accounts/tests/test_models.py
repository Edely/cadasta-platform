from datetime import datetime
from django.conf import settings
from django.test import TestCase
from .factories import UserFactory
from core.tests.utils.cases import UserTestCase
from unittest import mock
from ..models import VerificationDevice


class UserTest(TestCase):
    def test_repr(self):
        date = datetime.now()
        user = UserFactory.build(username='John',
                                 full_name='John Lennon',
                                 email='john@beatles.uk',
                                 email_verified=True,
                                 phone='+12025550111',
                                 phone_verified=True)
        assert repr(user) == ('<User username=John'
                              ' full_name=John Lennon'
                              ' email=john@beatles.uk'
                              ' email_verified=True'
                              ' phone=+12025550111'
                              ' phone_verified=True>').format(date)

    def test_avatar_url_property_with_avatar_field_empty(self):
        user = UserFactory.build(username='John',
                                 full_name='John Lennon',
                                 email='john@beatles.uk',
                                 )
        assert user.avatar_url == settings.DEFAULT_AVATAR

    def test_avatar_url_property_with_avatar_field_set(self):
        test_avatar_path = '/accounts/tests/files/avatar.png'
        user = UserFactory.build(username='John',
                                 full_name='John Lennon',
                                 email='john@beatles.uk',
                                 avatar=test_avatar_path,
                                 )
        assert user.avatar_url == user.avatar.url

    def test_language_verbose_property(self):
        user = UserFactory.build(username='John',
                                 email='john@beatles.uk',
                                 language='en',
                                 )
        assert user.language_verbose == 'English'

    def test_measurement_verbose_property(self):
        user = UserFactory.build(username='John',
                                 email='john@beatles.uk',
                                 measurement='metric',
                                 )
        assert user.measurement_verbose == 'Metric'


class VerificationDeviceTest(UserTestCase, TestCase):
    def setUp(self):
        super().setUp()

        self.sherlock = UserFactory.create(username='sherlock')
        VerificationDevice.objects.create(
            label='phone_verify',
            user=self.sherlock,
            unverified_phone=self.sherlock.phone)

        self.john = UserFactory.create(username='john')
        VerificationDevice.objects.create(
            label='phone_verify',
            user=self.john,
            unverified_phone=self.john.phone)

        self.TOTP_TOKEN_VALIDITY = settings.TOTP_TOKEN_VALIDITY
        self._now = 1497657600

    def test_instant(self):
        """Verify token as soon as it is created"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)

        with mock.patch('time.time', return_value=self._now):
            token = device.generate_challenge()
            verified = device.verify_token(int(token))

        assert verified is True

    def test_barely_made_it(self):
        """Verify token 1 second before it expires"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)

        with mock.patch('time.time', return_value=self._now):
            token = device.generate_challenge()
        with mock.patch('time.time',
                        return_value=self._now + self.TOTP_TOKEN_VALIDITY - 1):
            verified = device.verify_token(int(token))

        assert verified is True

    def test_too_late(self):
        """Verify token 1 second after it expires"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)

        with mock.patch('time.time', return_value=self._now):
            token = device.generate_challenge()
        with mock.patch('time.time',
                        return_value=self._now + self.TOTP_TOKEN_VALIDITY + 1):
            verified = device.verify_token(int(token))

        assert verified is False

    def test_future(self):
        """Verify token from the future. Time Travel!!"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)

        with mock.patch('time.time', return_value=self._now + 1):
            token = device.generate_challenge()
        with mock.patch('time.time', return_value=self._now - 1):
            verified = device.verify_token(int(token))

        assert verified is False

    def test_code_reuse(self):
        """Verify same token twice"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)

        token = device.generate_challenge()
        verified_once = device.verify_token(int(token))
        verified_twice = device.verify_token(int(token))

        assert verified_once is True
        assert verified_twice is False

    def test_cross_user(self):
        """Verify token generated by one device with that of another"""
        device_sherlock = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)
        device_john = self.john.verificationdevice_set.get(
            unverified_phone=self.john.phone)

        token = device_sherlock.generate_challenge()
        verified = device_john.verify_token(int(token))

        assert verified is False

    def test_token_tolerance(self):
        """Test tolerance of a token"""
        device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)
        with mock.patch('time.time', return_value=(
                self._now + (settings.TOTP_TOKEN_VALIDITY * 2))):
            token = device.generate_challenge()
        with mock.patch('time.time', return_value=self._now):
            verified = device.verify_token(token=int(token), tolerance=2)

        assert verified is True

    def test_verify_token_with_different_label(self):
        phone_device = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone,
            label='phone_verify')
        password_device = self.sherlock.verificationdevice_set.create(
            unverified_phone=self.sherlock.phone,
            label='password_reset')
        token = phone_device.generate_challenge()
        verified = password_device.verify_token(int(token))
        assert verified is False
