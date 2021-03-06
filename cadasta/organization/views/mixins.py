from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch

from tutelary.models import check_perms

from core.views.mixins import SuperUserCheckMixin
from ..models import Organization, Project, OrganizationRole, ProjectRole
from questionnaires.models import Questionnaire


class OrganizationMixin:
    def get_organization(self, lookup_kwarg='slug'):
        if lookup_kwarg == 'slug' and hasattr(self, 'org_lookup'):
            lookup_kwarg = self.org_lookup

        if not hasattr(self, 'org'):
            self.org = get_object_or_404(Organization,
                                         slug=self.kwargs[lookup_kwarg])
        return self.org

    def get_perms_objects(self):
        return [self.get_organization()]


class OrganizationRoles(OrganizationMixin):
    lookup_field = 'username'
    org_lookup = 'organization'

    def get_queryset(self):
        self.org = self.get_organization()
        return self.org.users.all()

    def get_serializer_context(self, *args, **kwargs):
        context = super(OrganizationRoles, self).get_serializer_context(
            *args, **kwargs)
        context['organization'] = self.get_organization()
        context['domain'] = get_current_site(self.request).domain
        context['sitename'] = settings.SITE_NAME
        return context


class ProjectMixin:
    def get_project(self):
        if not hasattr(self, 'prj'):
            self.prj = get_object_or_404(
                Project.objects.select_related('organization'),
                organization__slug=self.kwargs['organization'],
                slug=self.kwargs['project']
            )
        return self.prj

    def get_organization(self):
        if not hasattr(self, '_org'):
            self._org = self.get_project().organization
        return self._org

    def get_org_role(self):
        if not hasattr(self, '_org_role'):
            try:
                self._org_role = OrganizationRole.objects.get(
                    organization=self.get_project().organization,
                    user=self.request.user
                )
            except OrganizationRole.DoesNotExist:
                return None

        return self._org_role

    def get_prj_role(self):
        if self.request.user.is_anonymous:
            return None

        if not hasattr(self, '_prj_role'):
            try:
                self._prj_role = ProjectRole.objects.get(
                    project=self.get_project(),
                    user=self.request.user
                )
            except ProjectRole.DoesNotExist:
                return None

        return self._prj_role

    @property
    def is_administrator(self):
        if not hasattr(self, '_is_admin'):
            self._is_admin = False

            # Check if the user is anonymous: not an admin
            if isinstance(self.request.user, AnonymousUser):
                return False

            # Check if the user is a superuser: is an admin
            if self.is_superuser:
                self._is_admin = True
                return self._is_admin

            # Check if the user has the organization admin role: is an admin
            org_role = self.get_org_role()
            if org_role and org_role.admin:
                self._is_admin = True
                return self._is_admin

            # Check if the user has the project manager role: is an admin
            prj_role = self.get_prj_role()
            if prj_role and prj_role.role == 'PM':
                self._is_admin = True
                return self._is_admin

        return self._is_admin

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        prj_member = self.is_administrator or self.get_prj_role() is not None
        context['is_project_member'] = prj_member

        project = self.get_project()
        if project.current_questionnaire:
            q = Questionnaire.objects.get(id=project.current_questionnaire)
            context['form_lang_default'] = q.default_language

            question = q.questions.filter(~Q(label_xlat={})).first()
            if (question and isinstance(question.label_xlat, dict)):
                form_langs = [(l, settings.FORM_LANGS.get(l))
                              for l in question.label_xlat.keys()]
                context['form_langs'] = sorted(form_langs, key=lambda x: x[1])

        return context


class ProjectRoles(ProjectMixin):
    lookup_field = 'username'

    def get_perms_objects(self):
        return [self.get_project()]

    def get_queryset(self):
        self.prj = self.get_project()
        org = self.prj.organization
        orgs = Prefetch(
            'organizationrole_set',
            queryset=OrganizationRole.objects.filter(organization=org))
        prjs = Prefetch(
            'projectrole_set',
            queryset=ProjectRole.objects.filter(project=self.prj))
        return org.users.prefetch_related(orgs, prjs)

    def get_serializer_context(self, *args, **kwargs):
        context = super(ProjectRoles, self).get_serializer_context(
            *args, **kwargs)
        context['project'] = self.get_project()

        return context


class ProjectQuerySetMixin:
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            # superusers see all projects
            projects = Project.objects.all()
        else:
            # anyone can view public unarchived projects
            query = Q(access='public', archived=False)
            if not user.is_anonymous:
                # org/project members can view private unarchived projects
                query |= Q(
                    organization__organizationrole__user=user,
                    access='private', archived=False)
                # org admins can view archived projects
                query |= Q(
                    organization__organizationrole__user=user,
                    organization__organizationrole__admin=True)
                # project managers can view private/public archived/active prjs
                query |= Q(projectrole__user=user, projectrole__role='PM')
            projects = Project.objects.filter(query).distinct()
        return projects.select_related('organization').order_by(
            'organization__slug', 'slug')


class ProjectAdminCheckMixin(SuperUserCheckMixin):
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['is_administrator'] = self.is_administrator
        user = self.request.user

        project = self.get_project()
        permissions_contexts = (
            ('party.create', 'is_allowed_add_party'),
            ('spatial.create', 'is_allowed_add_location'),
            ('resource.add', 'is_allowed_add_resource'),
            ('project.import', 'is_allowed_import'),
            ('project.download', 'is_allowed_download'),
        )
        for permission_context in permissions_contexts:
            context[permission_context[1]] = user.has_perm(
                permission_context[0], project
            )

        return context


class ProjectCreateCheckMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_allow = None

    @property
    def add_allowed(self):
        if self.add_allow is None:
            if (hasattr(self, 'project_create_check_multiple') and
               self.project_create_check_multiple):
                self.add_allow = self.add_allowed_multiple()
            else:
                self.add_allow = self.add_allowed_single()
            self.add_allow = self.add_allow or self.is_superuser
        return self.add_allow

    def add_allowed_single(self):
        return check_perms(self.request.user, ('project.create',),
                           (self.get_object(),))

    def add_allowed_multiple(self):
        chk = False
        if Organization.objects.exists():
            u = self.request.user
            if hasattr(u, 'organizations'):
                chk = any([
                    check_perms(u, ('project.create',), (o,))
                    for o in u.organizations.all()
                ])
        return chk

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['add_allowed'] = self.add_allowed
        return context


class OrgRoleCheckMixin(SuperUserCheckMixin):
    def get_roles(self):
        if not hasattr(self, '_is_member') or not hasattr(self, '_is_admin'):
            self._is_member = False
            self._is_admin = False

            # Check if the user is anonymous: not an admin
            if isinstance(self.request.user, AnonymousUser):
                return False, False

            # Check if the user is a superuser: is an admin
            if self.is_superuser:
                self._is_member = True
                self._is_admin = True

            if hasattr(self, 'get_organization'):
                org = self.get_organization()
            else:
                org = self.get_object()
            try:
                role = OrganizationRole.objects.get(
                    organization=org,
                    user=self.request.user,
                )
                self._is_member = True
                self._is_admin = role.admin
            except OrganizationRole.DoesNotExist:
                pass

        return self._is_member, self._is_admin

    @property
    def is_administrator(self):
        _, admin = self.get_roles()
        return admin

    @property
    def is_member(self):
        member, _ = self.get_roles()
        return member

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['is_member'] = self.is_member
        context['is_administrator'] = self.is_administrator
        return context
