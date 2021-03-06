import pytest
import datetime
from unittest import mock
from django.core.urlresolvers import reverse_lazy
from django.utils import translation
from django.test import TestCase
from django.core import mail
from skivvy import ViewTestCase
from twilio.base.exceptions import TwilioRestException

from accounts.tests.factories import UserFactory
from core.tests.utils.cases import UserTestCase

from allauth.account.models import EmailConfirmation, EmailAddress
from allauth.account.forms import ChangePasswordForm

from accounts.models import User, VerificationDevice
from ..views import default
from ..forms import ProfileForm
from organization.models import OrganizationRole, ProjectRole
from organization.tests.factories import ProjectFactory, OrganizationFactory
from ..messages import account_inactive, unverified_identifier, TWILIO_ERRORS


class RegisterTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.AccountRegister
    template = 'accounts/signup.html'

    def test_signs_up_with_invalid(self):
        data = {
            'username': 'sherlock',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        assert User.objects.count() == 0
        assert VerificationDevice.objects.count() == 0
        assert len(mail.outbox) == 0

    def test_signs_up_with_phone_only(self):
        data = {
            'username': 'sherlock',
            'phone': '+919327768250',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'en'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert User.objects.count() == 1
        assert VerificationDevice.objects.count() == 1
        assert len(mail.outbox) == 0
        assert 'account/accountverification/' in response.location

    def test_signs_up_with_email_only(self):
        data = {
            'username': 'sherlock',
            'email': 'sherlock.holmes@bbc.uk',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'en'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert User.objects.count() == 1
        assert VerificationDevice.objects.count() == 0
        assert len(mail.outbox) == 1
        assert 'account/accountverification/' in response.location

    def test_signs_up_sets_language(self):
        data = {
            'username': 'sherlock',
            'email': 'sherlock.holmes@bbc.uk',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'es'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert User.objects.count() == 1
        assert 'account/accountverification/' in response.location
        assert translation.get_language() == 'es'

        # Reset language for following tests
        translation.activate('en')

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_sign_up_with_invalid_phone_number(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Unable to create record: The "To" number +15555555555 is '
                 'not a valid phone number.'),
            method='POST',
            code=21211
        )
        data = {
            'username': 'sherlock',
            'phone': '+15555555555',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'en'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        assert TWILIO_ERRORS[21211] in response.content
        assert User.objects.count() == 0
        assert VerificationDevice.objects.count() == 0
        assert len(mail.outbox) == 0

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_400(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        data = {
            'username': 'sherlock',
            'phone': '+15555555555',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'en'
        }
        with pytest.raises(TwilioRestException):
            self.request(method='POST', post_data=data)
            assert User.objects.count() == 0
            assert VerificationDevice.objects.count() == 0
            assert len(mail.outbox) == 0

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_500(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=500,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        data = {
            'username': 'sherlock',
            'phone': '+15555555555',
            'password': '221B@bakerstreet',
            'full_name': 'Sherlock Holmes',
            'language': 'en'
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        assert TWILIO_ERRORS['default'] in response.content
        self.request(method='POST', post_data=data)
        assert User.objects.count() == 0
        assert VerificationDevice.objects.count() == 0
        assert len(mail.outbox) == 0


class ProfileTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.AccountProfile
    template = 'accounts/profile.html'

    def setup_template_context(self):
        return {
            'form': ProfileForm(instance=self.user),
            'emails_to_verify': False,
            'phones_to_verify': False
        }

    def test_get_profile(self):
        self.user = UserFactory.create()
        response = self.request(user=self.user)

        assert response.status_code == 200
        assert response.content == self.expected_content

    def test_get_profile_with_unverified_email(self):
        self.user = UserFactory.create()
        EmailAddress.objects.create(
            user=self.user,
            email='miles2@davis.co',
            verified=False,
            primary=True
        )
        response = self.request(user=self.user)

        assert response.status_code == 200
        assert response.content == self.render_content(emails_to_verify=True)

    def test_get_profile_with_verified_email(self):
        self.user = UserFactory.create()
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            verified=True,
            primary=True
        )
        response = self.request(user=self.user)

        assert response.status_code == 200
        assert response.content == self.expected_content

    def test_update_profile(self):
        user = UserFactory.create(username='John',
                                  password='sgt-pepper')
        post_data = {
            'username': 'John',
            'email': user.email,
            'phone': user.phone,
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'John Lennon',
            'password': 'sgt-pepper',
        }
        response = self.request(method='POST', post_data=post_data, user=user)
        response.status_code == 200

        user.refresh_from_db()
        assert user.full_name == 'John Lennon'

    def test_get_profile_when_no_user_is_signed_in(self):
        response = self.request()
        assert response.status_code == 302
        assert '/account/login/' in response.location

    def test_update_profile_when_no_user_is_signed_in(self):
        response = self.request(method='POST', post_data={})
        assert response.status_code == 302
        assert '/account/login/' in response.location

    def test_update_profile_duplicate_email(self):
        user1 = UserFactory.create(username='John',
                                   full_name='John Lennon')
        user2 = UserFactory.create(username='Bill')
        post_data = {
            'username': 'Bill',
            'email': user1.email,
            'phone': user2.phone,
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Bill Bloggs',
        }

        response = self.request(method='POST', user=user2, post_data=post_data)
        assert 'Failed to update profile information' in response.messages

    def test_get_profile_with_verified_phone(self):
        self.user = UserFactory.create(phone_verified=True,
                                       email_verified=True)
        response = self.request(user=self.user)

        assert response.status_code == 200
        assert response.content == self.expected_content

    def test_get_profile_with_unverified_phone(self):
        self.user = UserFactory.create()
        VerificationDevice.objects.create(
            user=self.user, unverified_phone=self.user.phone)

        response = self.request(user=self.user)

        assert response.status_code == 200
        assert response.content == self.render_content(phones_to_verify=True)

    def test_update_profile_with_duplicate_phone(self):
        user1 = UserFactory.create(phone='+919327768250')
        user2 = UserFactory.create(password='221B@bakerstreet')
        post_data = {
            'username': user2.username,
            'email': user2.email,
            'phone': user1.phone,
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        response = self.request(method='POST', post_data=post_data, user=user2)

        assert response.status_code == 200
        assert 'Failed to update profile information' in response.messages

    def test_update_profile_with_phone(self):
        user = UserFactory.create(password='221B@bakerstreet')
        post_data = {
            'username': user.username,
            'email': user.email,
            'phone': '+919327768250',
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        response = self.request(method='POST', post_data=post_data, user=user)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_update_profile_with_invalid_phone(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Unable to create record: The "To" number +15555555555 is '
                 'not a valid phone number.'),
            method='POST',
            code=21211
        )
        user = UserFactory.create(password='221B@bakerstreet')
        post_data = {
            'username': 'new_name',
            'email': user.email,
            'phone': '+919327768250',
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        response = self.request(method='POST', post_data=post_data, user=user)
        assert response.status_code == 200
        assert TWILIO_ERRORS[21211] in response.content
        assert VerificationDevice.objects.count() == 0
        user.refresh_from_db()
        assert user.username != 'new_name'

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_400(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        user = UserFactory.create(password='221B@bakerstreet')
        post_data = {
            'username': 'new_name',
            'email': user.email,
            'phone': '+919327768250',
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        with pytest.raises(TwilioRestException):
            self.request(method='POST', post_data=post_data, user=user)
        assert VerificationDevice.objects.count() == 0
        user.refresh_from_db()
        assert user.username != 'new_name'

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_500(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=500,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        user = UserFactory.create(password='221B@bakerstreet')
        post_data = {
            'username': 'new_name',
            'email': user.email,
            'phone': '+919327768250',
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        response = self.request(method='POST', post_data=post_data, user=user)
        assert response.status_code == 200
        assert TWILIO_ERRORS['default'] in response.content
        assert VerificationDevice.objects.count() == 0
        user.refresh_from_db()
        assert user.username != 'new_name'

    def test_update_keep_phone(self):
        user = UserFactory.create(
            password='221B@bakerstreet')
        post_data = {
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'language': 'en',
            'measurement': 'metric',
            'full_name': 'Sherlock Holmes',
            'password': '221B@bakerstreet'
        }
        response = self.request(method='POST', post_data=post_data, user=user)
        assert response.status_code == 302
        assert '/account/dashboard/' in response.location


class PasswordChangeTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.PasswordChangeView
    success_url = reverse_lazy('account:profile')

    def setup_template_context(self):
        return {
            'form': ChangePasswordForm(instance=self.user)
        }

    def test_password_change(self):
        self.user = UserFactory.create(password='Noonewillguess!')
        data = {'oldpassword': 'Noonewillguess!',
                'password': 'Someonemightguess?'}
        response = self.request(method='POST', post_data=data, user=self.user)

        assert response.status_code == 302
        assert response.location == self.expected_success_url
        assert self.user.check_password('Someonemightguess?') is True


class LoginTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.AccountLogin

    def setup_models(self):
        self.user = UserFactory.create(username='imagine71',
                                       email='john@beatles.uk',
                                       phone='+919327768250',
                                       password='iloveyoko79')

    def test_successful_login(self):
        self.user.email_verified = True
        self.user.save()

        data = {'login': 'imagine71', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert 'dashboard' in response.location

    def test_successful_login_with_unverified_user(self):
        self.user.email_verified = False
        self.user.phone_verified = False
        self.user.save()

        data = {'login': 'imagine71', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/resendtokenpage/' in response.location
        assert account_inactive in response.messages

        self.user.refresh_from_db()
        assert self.user.is_active is False

    def test_unsuccessful_login_with_email(self):

        data = {'login': 'john@beatles.uk', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/resendtokenpage/' in response.location
        assert unverified_identifier in response.messages

    def test_unsuccessful_login_with_phone(self):
        data = {'login': '+919327768250', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/resendtokenpage/' in response.location
        assert unverified_identifier in response.messages

    def test_successful_login_with_username_both_verified(self):
        self.user.email_verified = True
        self.user.phone_verified = True
        self.user.save()

        data = {'login': 'imagine71', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert 'dashboard' in response.location

    def test_successful_login_with_username_only_phone_verified(self):
        self.user.phone_verified = True
        self.user.save()

        data = {'login': 'imagine71', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert 'dashboard' in response.location

    def test_successful_login_with_email(self):
        self.user.email_verified = True
        self.user.save()

        data = {'login': 'john@beatles.uk', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert 'dashboard' in response.location

    def test_successful_login_with_phone(self):
        self.user.phone_verified = True
        self.user.save()

        data = {'login': '+919327768250', 'password': 'iloveyoko79'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert 'dashboard' in response.location


class ConfirmEmailTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.ConfirmEmail
    url_kwargs = {'key': '123'}

    def setup_models(self):
        self.user = UserFactory.create(email='john@example.com')
        self.email_address = EmailAddress.objects.create(
            user=self.user,
            email='john@example.com',
            verified=False,
            primary=True
        )
        self.confirmation = EmailConfirmation.objects.create(
            email_address=self.email_address,
            sent=datetime.datetime.now(),
            key='123'
        )

    def test_activate(self):
        response = self.request(user=self.user)
        assert response.status_code == 302
        assert 'dashboard' in response.location

        self.user.refresh_from_db()
        assert self.user.email_verified is True
        assert self.user.is_active is True

        self.email_address.refresh_from_db()
        assert self.email_address.verified is True

    def test_activate_changed_email(self):
        self.email_address.email = 'john2@example.com'
        self.email_address.save()

        EmailConfirmation.objects.create(
            email_address=self.email_address,
            sent=datetime.datetime.now(),
            key='456'
        )
        response = self.request(user=self.user, url_kwargs={'key': '456'})
        assert response.status_code == 302
        assert 'dashboard' in response.location

        self.user.refresh_from_db()
        assert self.user.email_verified is True
        assert self.user.is_active is True
        assert self.user.email == 'john2@example.com'

        self.email_address.refresh_from_db()
        assert self.email_address.verified is True

    def test_activate_with_invalid_token(self):
        response = self.request(user=self.user, url_kwargs={'key': 'abc'})
        assert response.status_code == 200

        self.user.refresh_from_db()
        assert self.user.email_verified is False
        assert self.user.is_active is True

        self.email_address.refresh_from_db()
        assert self.email_address.verified is False


class PasswordResetViewTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.PasswordResetView

    def setup_models(self):
        self.user = UserFactory.create(email='john@example.com',
                                       phone='+919327762850')
        self.user.verificationdevice_set.create(
            unverified_phone=self.user.phone,
            label='password_reset')

    def test_mail_sent(self):
        data = {'email': 'john@example.com'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert len(mail.outbox) == 1

    def test_mail_not_sent(self):
        data = {'email': 'abcd@example.com'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert len(mail.outbox) == 0

    def test_text_msg_sent(self):
        data = {'phone': '+919327762850'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302

    def test_text_msg_not_sent(self):
        data = {'phone': '+12345678990'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_send_token_with_invalid_phone(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Unable to create record: The "To" number +15555555555 is '
                 'not a valid phone number.'),
            method='POST',
            code=21211
        )
        data = {'phone': '+919327762850'}
        response = self.request(method='POST', post_data=data)

        assert response.status_code == 200
        assert TWILIO_ERRORS[21211] in response.content

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_400(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        data = {'phone': '+919327762850'}
        with pytest.raises(TwilioRestException):
            self.request(method='POST', post_data=data)

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_500(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=500,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        data = {'phone': '+919327762850'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        assert TWILIO_ERRORS['default'] in response.content


class PasswordResetDoneViewTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.PasswordResetDoneView

    def setup_models(self):
        self.user = UserFactory.create(phone='+919327768250',
                                       email='sherlock.holmes@bbc.uk',
                                       phone_verified=True,
                                       email_verified=True)
        self.device = VerificationDevice.objects.create(
            user=self.user,
            unverified_phone=self.user.phone,
            label='password_reset')

    def test_successful_token_verification(self):
        token = self.device.generate_challenge()
        data = {'token': token}
        response = self.request(
            method='POST',
            post_data=data,
            session_data={"phone": self.user.phone})

        assert response.status_code == 302
        assert '/account/password/reset/phone/' in response.location
        assert VerificationDevice.objects.filter(
            user=self.user, label='password_reset').exists() is False

    def test_without_phone(self):
        token = self.device.generate_challenge()
        data = {'token': token}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200

    def test_with_unknown_phone(self):
        token = self.device.generate_challenge()
        data = {'token': token}
        response = self.request(
            method='POST',
            post_data=data,
            session_data={"phone": '+12345678990'})

        assert response.status_code == 200


class PasswordResetFromPhoneViewTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.PasswordResetFromPhoneView

    def setup_models(self):
        self.user = UserFactory.create(password='221B@bakerstreet')

    def test_password_successfully_set(self):
        data = {'password': 'i@msher!0cked'}
        response = self.request(
            method='POST',
            post_data=data,
            session_data={"password_reset_id": self.user.id})
        assert response.status_code == 302
        self.user.refresh_from_db()
        assert self.user.check_password('i@msher!0cked') is True
        assert len(mail.outbox) == 1
        assert self.user.email in mail.outbox[0].to

    def test_password_set_without_password_reset_id(self):
        data = {'password': 'i@msher!0cked'}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        self.user.refresh_from_db()
        assert self.user.check_password('i@msher!0cked') is False


class ConfirmPhoneViewTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.ConfirmPhone

    def setup_models(self):
        self.user = UserFactory.create(phone='+919327768250')
        EmailAddress.objects.create(user=self.user, email=self.user.email)

    def test_successful_phone_verification(self):
        device = VerificationDevice.objects.create(
            user=self.user, unverified_phone=self.user.phone)
        token = device.generate_challenge()

        data = {'token': token}
        response = self.request(
            method='POST',
            post_data=data,
            session_data={'phone_verify_id': self.user.id})
        assert response.status_code == 302

        self.user.refresh_from_db()
        assert self.user.phone_verified is True
        assert VerificationDevice.objects.filter(
            user=self.user,
            unverified_phone=self.user.phone,
            label='phone_verify').exists() is False

    def test_successful_new_phone_verification(self):
        device = VerificationDevice.objects.create(
            user=self.user, unverified_phone='+12345678990')
        token = device.generate_challenge()

        data = {'token': token}
        response = self.request(
            method='POST',
            post_data=data,
            session_data={'phone_verify_id': self.user.id})
        assert response.status_code == 302

        self.user.refresh_from_db()
        assert self.user.phone == '+12345678990'
        assert self.user.phone_verified is True
        assert VerificationDevice.objects.filter(
            user=self.user,
            unverified_phone='+12345678990',
            label='phone_verify').exists() is False

    def test_phone_verification_without_phone_verify_id(self):
        device = VerificationDevice.objects.create(
            user=self.user, unverified_phone=self.user.phone)
        token = device.generate_challenge()

        data = {'token': token}
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200


class ResendTokenViewTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.ResendTokenView

    def setup_models(self):
        self.user = UserFactory.create(username='sherlock',
                                       email='sherlock.holmes@bbc.uk',
                                       phone='+919327768250',
                                       password='221B@bakerstreet',
                                       )

    def test_phone_send_token(self):
        VerificationDevice.objects.create(user=self.user,
                                          unverified_phone=self.user.phone)
        data = {
            'phone': '+919327768250',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_send_token_with_invalid_phone(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Unable to create record: The "To" number +15555555555 is '
                 'not a valid phone number.'),
            method='POST',
            code=21211
        )
        VerificationDevice.objects.create(user=self.user,
                                          unverified_phone=self.user.phone)
        data = {
            'phone': '+919327768250',
        }
        response = self.request(method='POST', post_data=data)

        assert response.status_code == 200
        assert TWILIO_ERRORS[21211] in response.content

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_400(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=400,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        VerificationDevice.objects.create(user=self.user,
                                          unverified_phone=self.user.phone)
        data = {
            'phone': '+919327768250',
        }
        with pytest.raises(TwilioRestException):
            self.request(method='POST', post_data=data)

    @mock.patch('accounts.gateways.FakeGateway.send_sms')
    def test_twilio_error_500(self, send_sms):
        send_sms.side_effect = TwilioRestException(
            status=500,
            uri='http://localhost:8000',
            msg=('Account not active'),
            method='POST',
            code=20005
        )
        VerificationDevice.objects.create(user=self.user,
                                          unverified_phone=self.user.phone)
        data = {
            'phone': '+919327768250',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 200
        assert TWILIO_ERRORS['default'] in response.content

    def test_email_send_link(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email)
        data = {
            'email': 'sherlock.holmes@bbc.uk',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location
        assert len(mail.outbox) == 1
        assert 'sherlock.holmes@bbc.uk' in mail.outbox[0].to
        assert len(response.messages) == 1
        assert ('Confirmation email sent to sherlock.holmes@bbc.uk.'
                not in response.messages)

    def test_updated_email_send_link(self):
        EmailAddress.objects.create(user=self.user, email='john.watson@bbc.uk')
        data = {
            'email': 'john.watson@bbc.uk',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location
        assert len(mail.outbox) == 1
        assert 'john.watson@bbc.uk' in mail.outbox[0].to

    def test_already_verified_email(self):
        EmailAddress.objects.create(
            user=self.user, verified=True, email=self.user.email)
        data = {
            'email': 'john.watson@bbc.uk',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location
        assert len(mail.outbox) == 0

    def test_already_verified_phone(self):
        data = {
            'phone': '+919327768250',
        }
        response = self.request(method='POST', post_data=data)
        assert response.status_code == 302
        assert '/account/accountverification/' in response.location
        assert VerificationDevice.objects.filter(
            user=self.user,
            unverified_phone=self.user.phone,
            label='phone_verify').exists() is False


class UserDashboardTest(ViewTestCase, UserTestCase, TestCase):
    view_class = default.UserDashboard
    template = 'accounts/user_dashboard.html'

    def test_with_anonymous_user(self):
        response = self.request()

        assert response.status_code == 302
        assert '/account/login/' in response.location

    def test_without_organizations(self):
        user = UserFactory.create()

        response = self.request(user=user)

        assert response.status_code == 200
        assert response.content == self.render_content(
            user_orgs_and_projects=[])

    def test_with_organizations_without_projects(self):
        user = UserFactory.create()
        org = OrganizationFactory.create()
        orgrole = OrganizationRole.objects.create(organization=org, user=user)

        response = self.request(user=user)

        assert response.status_code == 200
        assert response.content == self.render_content(
            user_orgs_and_projects=[(org, orgrole.admin, [])])

    def test_with_organizations_and_projects(self):
        user = UserFactory.create()
        org1, org2 = OrganizationFactory.create_batch(2)

        proj1, proj2 = ProjectFactory.create_batch(2, organization=org1)
        proj3 = ProjectFactory.create(organization=org2)
        proj4 = ProjectFactory.create(organization=org2, archived=False)

        ProjectRole.objects.create(project=proj1, user=user, role='DC')
        is_not_admin_org1 = OrganizationRole.objects.create(
            organization=org1, user=user, admin=False).admin
        is_admin_org2 = OrganizationRole.objects.create(
            organization=org2, user=user, admin=True).admin

        response = self.request(user=user)

        assert response.status_code == 200
        assert response.content == self.render_content(
            user_orgs_and_projects=[
                (org1, is_not_admin_org1, [
                    (proj2, 'Public User'),
                    (proj1, 'Data Collector')]),
                (org2, is_admin_org2, [
                    (proj3, 'Administrator'),
                    (proj4, 'Administrator')]),
                ])
