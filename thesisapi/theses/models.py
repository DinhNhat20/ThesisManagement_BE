from django.db import models
from django.contrib.auth.models import AbstractUser
from ckeditor.fields import RichTextField
from cloudinary.models import CloudinaryField


class BaseModel(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class UserBaseModel(models.Model):
    code = models.CharField(max_length=10, unique=True)
    full_name = models.CharField(max_length=50, null=False)
    birthday = models.DateField(null=False)
    address = models.CharField(max_length=100, null=False)

    class Meta:
        abstract = True


class Role(models.Model):  # Vai trò (Quản trị viên, Giáo vụ, Giảng viên, Sinh viên)
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=30, unique=True, null=False)

    def __str__(self):
        return self.name


class User(AbstractUser):  # Người dùng
    Gender_choice = [
        ('Nam', 'Nam'),
        ('Nữ', 'Nữ')
    ]
    avatar = CloudinaryField(null=True)
    phone = models.CharField(max_length=10, null=False)
    gender = models.CharField(max_length=10, null=False, choices=Gender_choice)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    def has_role(self, required_role):
        return self.role == required_role

    def save(self, *args, **kwargs):
        if not self.pk and self.is_superuser:
            self.role = Role.objects.get(code='admin')
        super().save(*args, **kwargs)

        # if not self.avatar:
        #     self.avatar = 'image/upload/v1713421473/user.png'
        # super().save(*args, **kwargs)


class Ministry(UserBaseModel):  # Giáo vụ
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)

    def __str__(self):
        return self.full_name


class Position(models.Model):  # Vị trí
    name = models.CharField(max_length=15, null=False)

    def __str__(self):
        return self.name


class SchoolYear(models.Model):  # Năm học
    name = models.CharField(max_length=15, null=False)
    start_year = models.DateField()
    end_year = models.DateField()

    def __str__(self):
        return self.name


class Faculty(models.Model):  # Khoa
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=50, null=False)

    def __str__(self):
        return self.name


class Major(models.Model):  # Ngành
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=50, null=False)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Lecturer(UserBaseModel):  # Giảng viên
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE)

    def __str__(self):
        return self.full_name


class Council(models.Model):  # Hội đồng
    name = models.CharField(max_length=50, null=False, unique=True)
    description = models.CharField(max_length=50, null=False)
    is_lock = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class CouncilDetail(models.Model):  # Chi tiết hội đồng
    lecturer = models.ForeignKey(Lecturer, on_delete=models.CASCADE)
    council = models.ForeignKey(Council, on_delete=models.CASCADE)
    position = models.ForeignKey(Position, on_delete=models.PROTECT)


class Thesis(models.Model):  # Khóa luận
    code = models.CharField(max_length=10, null=False, primary_key=True)
    name = models.CharField(max_length=200, null=False)
    start_date = models.DateField()
    end_date = models.DateField()
    report_file = RichTextField(null=True, blank=True)
    total_score = models.FloatField(null=True, default=0)
    result = models.BooleanField(default=False)
    major = models.ForeignKey(Major, on_delete=models.PROTECT)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT)
    council = models.ForeignKey(Council, on_delete=models.PROTECT, null=True, blank=True)
    lecturers = models.ManyToManyField(Lecturer, null=True, blank=True)  # Giảng viên hướng dẫn khóa luận (Tối đa 2)

    def __str__(self):
        return self.name


class Supervisor(models.Model):
    lecturer = models.ForeignKey(Lecturer, on_delete=models.PROTECT)
    thesis = models.ForeignKey(Thesis, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.lecturer} hướng dẫn {self.thesis}"


class Student(UserBaseModel):  # Sinh viên
    gpa = models.FloatField()
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    major = models.ForeignKey(Major, on_delete=models.PROTECT)
    thesis = models.ForeignKey(Thesis, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.full_name


class Criteria(models.Model):  # Tiêu chí (Ví dụ: Kiến thức chuyên môn, phương pháp nghiên cứu, kỹ năng trình bày)
    name = models.CharField(max_length=150, null=False)
    evaluation_method = models.CharField(max_length=255, null=True)  # Phương pháp đánh giá

    def __str__(self):
        return self.name


class ThesisCriteria(models.Model):  # Tiêu chí của khóa luận
    thesis = models.ForeignKey(Thesis, on_delete=models.CASCADE)
    criteria = models.ForeignKey(Criteria, on_delete=models.CASCADE)
    weight = models.FloatField(null=False)  # Trọng số (%)


class Score(models.Model):  # Điểm cho tiêu chí
    thesis_criteria = models.ForeignKey(ThesisCriteria, on_delete=models.CASCADE)
    council_detail = models.ForeignKey(CouncilDetail, on_delete=models.PROTECT)
    score_number = models.FloatField(null=False)  # 0 - 10


class Post(BaseModel):  # Bài đăng
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = RichTextField()


class Interaction(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Like(Interaction):  # Thích
    unique_together = ('post', 'user')


class Comment(Interaction):  # Bình luận
    content = models.CharField(max_length=255)
