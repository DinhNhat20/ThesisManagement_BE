from cloudinary.templatetags import cloudinary
from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.db.models import Avg, Count, Q
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import mark_safe
from oauth2_provider.models import Application, AccessToken, RefreshToken
from theses.models import Role, User, Ministry, Position, SchoolYear, Faculty, Major, Lecturer, Student, Council, \
    CouncilDetail, Thesis, Criteria, ThesisCriteria, Score, Post, Like, Comment


class MyAdminSite(admin.AdminSite):
    site_header = 'THESIS MANAGEMENT'
    index_title = 'Thesis Management'
    site_title = 'Admin'

    def get_urls(self):
        return [path('thesis-stats/', self.stats)] + super().get_urls()

    # def get_urls(self):
    #     urls = super().get_urls()
    #     custom_urls = [
    #         path('thesis-stats/', self.stats, name='stats'),
    #     ]
    #     return custom_urls + urls

    def stats(self, request):
        avg_score_by_school_year = Thesis.objects.values('school_year__name').annotate(avg_score=Avg('total_score'))

        for item in avg_score_by_school_year:
            item['avg_score'] = round(item['avg_score'], 2)

        thesis_major_count = Major.objects.annotate(thesis_count=Count('thesis'))

        result = Thesis.objects.values('school_year__name').annotate(
            pass_count=Count('code', filter=Q(result=True)),
            fail_count=Count('code', filter=Q(result=False)),
        ).order_by('school_year__start_year')

        return TemplateResponse(request, 'admin/stats.html', {
            'avg_score_by_school_year': avg_score_by_school_year,
            'thesis_major_count': thesis_major_count,
            'result': result
        })


class MyRoleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']


class MyUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'first_name', 'last_name', 'email', 'phone', 'gender', 'role']
    search_fields = ['username', 'first_name', 'last_name']
    list_filter = ['gender', 'role']
    readonly_fields = ['user_avatar']

    # Băm mật khẩu khi tạo user
    def save_model(self, request, obj, form, change):
        if not change:
            obj.password = make_password(form.cleaned_data['password'])
        super().save_model(request, obj, form, change)

    def user_avatar(self, user):
        if user.avatar:
            if type(user.avatar) is cloudinary.CloudinaryResource:
                return mark_safe(f"<img width='100' src='{user.avatar.url}' />")
            return mark_safe(f"<img width='100' src='/static/{user.avatar.name}' />")
        else:
            return "No avatar"


class MyMinistryAdmin(admin.ModelAdmin):
    list_display = ['code', 'full_name', 'birthday', 'address', 'user']


class MyPositionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


class MySchoolYearAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'start_year', 'end_year']
    search_fields = ['name']


class MyFacultyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


class MyMajorAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'faculty']
    search_fields = ['code', 'name']
    list_filter = ['faculty']


class MyLecturerAdmin(admin.ModelAdmin):
    list_display = ['code', 'full_name', 'birthday', 'address', 'faculty', 'user_id']
    search_fields = ['code', 'full_name']
    list_filter = ['faculty']


class MyStudentAdmin(admin.ModelAdmin):
    list_display = ['code', 'full_name', 'birthday', 'address', 'gpa', 'user_id', 'major', 'thesis']
    search_fields = ['code', 'full_name']
    list_filter = ['major']


class MyCouncilAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'description', 'is_lock']
    search_fields = ['name']
    list_filter = ['is_lock']


class MyCouncilDetailAdmin(admin.ModelAdmin):
    list_display = ['id', 'lecturer', 'council', 'position']
    list_filter = ['council']


class MyThesisAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'start_date', 'end_date', 'total_score', 'result', 'major', 'council']
    search_fields = ['name', 'major']
    list_filter = ['major', 'school_year']


class MyCriteriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'evaluation_method']
    search_fields = ['name']


class MyThesisCriteriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'thesis', 'criteria', 'weight']
    search_fields = ['thesis']


class MyScoreAdmin(admin.ModelAdmin):
    list_display = ['id', 'thesis_criteria', 'council_detail', 'score_number']


class MyPostAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'content', 'created_date', 'updated_date', 'active']
    search_fields = ['content']


class MyLikeAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'post', 'created_date', 'updated_date', 'active']


class MyCommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'post', 'content', 'created_date', 'updated_date', 'active']
    search_fields = ['content']


class MyApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'client_id', 'user', 'client_type')


class MyAccessTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'application', 'expires', 'scope')


class MyRefreshTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'access_token', 'application')


admin_site = MyAdminSite(name='ThesisManagementApp')

admin_site.register(Role, MyRoleAdmin)
admin_site.register(User, MyUserAdmin)
admin_site.register(Ministry, MyMinistryAdmin)
admin_site.register(Position, MyPositionAdmin)
admin_site.register(SchoolYear, MySchoolYearAdmin)
admin_site.register(Faculty, MyFacultyAdmin)
admin_site.register(Major, MyMajorAdmin)
admin_site.register(Lecturer, MyLecturerAdmin)
admin_site.register(Student, MyStudentAdmin)
admin_site.register(Council, MyCouncilAdmin)
admin_site.register(CouncilDetail, MyCouncilDetailAdmin)
admin_site.register(Thesis, MyThesisAdmin)
admin_site.register(Criteria, MyCriteriaAdmin)
admin_site.register(ThesisCriteria, MyThesisCriteriaAdmin)
admin_site.register(Score, MyScoreAdmin)
admin_site.register(Post, MyPostAdmin)
admin_site.register(Like, MyLikeAdmin)
admin_site.register(Comment, MyCommentAdmin)
admin_site.register(Application, MyApplicationAdmin)
admin_site.register(AccessToken, MyAccessTokenAdmin)
admin_site.register(RefreshToken, MyRefreshTokenAdmin)
