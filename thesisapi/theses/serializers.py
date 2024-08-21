from rest_framework import serializers
from theses.models import Student, Lecturer, Ministry, User, Position, SchoolYear, Faculty, Major, Council, \
    CouncilDetail, Thesis, Score, Criteria, ThesisCriteria, Post, Comment


# Người dùng
class UserSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    lecturer = serializers.SerializerMethodField()
    ministry = serializers.SerializerMethodField()

    # Lấy thông tin của sinh viên, giảng viên, giáo vụ
    def get_student(self, obj):
        try:
            student = Student.objects.get(user=obj)
            return StudentSerializer(student).data
        except Student.DoesNotExist:
            return None

    def get_lecturer(self, obj):
        try:
            lecturer = Lecturer.objects.get(user=obj)
            return LecturerSerializer(lecturer).data
        except Lecturer.DoesNotExist:
            return None

    def get_ministry(self, obj):
        try:
            ministry = Ministry.objects.get(user=obj)
            return MinistrySerializer(ministry).data
        except Ministry.DoesNotExist:
            return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        avatar = getattr(instance, 'avatar', None)
        if avatar:
            rep['avatar'] = instance.avatar.url

        # Loại bỏ trường student, lecturer, ministry nếu không tồn tại
        if rep.get('student') is None:
            rep.pop('student')

        if rep.get('lecturer') is None:
            rep.pop('lecturer')

        if rep.get('ministry') is None:
            rep.pop('ministry')

        return rep

    def create(self, validated_data):
        data = validated_data.copy()
        user = User(**data)
        user.set_password(user.password)
        user.save()

        return user

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'first_name', 'last_name',
                  'email', 'phone', 'gender', 'avatar', 'role', 'student', 'lecturer', 'ministry']

        extra_kwargs = {
            'password': {
                'write_only': True
            }
        }


# Giáo vụ
class MinistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Ministry
        fields = ['code', 'full_name', 'birthday', 'address', 'user']


# Vị trí
class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = '__all__'


# Năm học
class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolYear
        fields = '__all__'


# Khoa
class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ['code', 'name']


# Ngành
class MajorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Major
        fields = ['code', 'name', 'faculty']

    # Trả về tên khoa khi GET
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['faculty'] = instance.faculty.name if instance.faculty else None
        return rep


# Giảng viên
class LecturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lecturer
        fields = ['user', 'code', 'full_name', 'birthday', 'address', 'faculty']

    # Trả về tên khoa khi GET
    def to_representation(self, instance): # to_representation được ghi đè để thay đổi cách hiển thị
        rep = super().to_representation(instance)
        rep['faculty'] = instance.faculty.name if instance.faculty else None
        return rep


# Sinh viên
class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['user', 'code', 'full_name', 'birthday', 'address', 'gpa', 'major', 'thesis']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['major'] = instance.major.name if instance.major else None
        return rep


# Hội đồng
class CouncilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Council
        fields = ['id', 'name', 'description', 'is_lock']


# Chi tiết hội đồng
class CouncilDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = CouncilDetail
        fields = ['id', 'lecturer', 'council', 'position']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['lecturer'] = instance.lecturer.full_name if instance.lecturer else None
        rep['council'] = instance.council.name if instance.council else None
        rep['position'] = instance.position.name if instance.position else None
        return rep


# Lấy thêm ID và name để thuận tiện cho xử lý lấy hội đồng gv tham gia
class CouncilDetailWithIDSerializer(serializers.ModelSerializer):
    council_id = serializers.PrimaryKeyRelatedField(source='council.id', queryset=Council.objects.all())
    council_name = serializers.CharField(source='council.name', read_only=True)

    class Meta:
        model = CouncilDetail
        fields = ['id', 'council_id', 'council_name', 'lecturer', 'position']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['lecturer'] = instance.lecturer.full_name if instance.lecturer else None
        rep['position'] = instance.position.name if instance.position else None
        return rep


# Khóa luận
class ThesisSerializer(serializers.ModelSerializer):
    lecturers = serializers.SerializerMethodField()
    reviewer = serializers.SerializerMethodField()
    students = serializers.SerializerMethodField()

    def get_students(self, obj):
        students_queryset = obj.student_set.all()
        return StudentSerializer(students_queryset, many=True).data

    def get_lecturers(self, obj):
        lecturers_queryset = obj.lecturers.all()
        return LecturerSerializer(lecturers_queryset, many=True).data

    def get_reviewer(self, obj):
        if obj.council:
            reviewer_detail = obj.council.councildetail_set.filter(position__name='Phản biện').first()
            if reviewer_detail:
                return LecturerSerializer(reviewer_detail.lecturer).data
        return None

    class Meta:
        model = Thesis
        fields = ['code', 'name', 'start_date', 'end_date', 'report_file',
                  'total_score', 'result', 'council', 'major',
                  'school_year', 'students', 'lecturers', 'reviewer']

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep['council'] = instance.council.name if instance.council else None
        rep['major'] = instance.major.name if instance.major else None
        rep['school_year'] = instance.school_year.name if instance.school_year else None

        return rep


# Điểm
class ScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Score
        fields = ['thesis_criteria', 'council_detail', 'score_number']


# Tiêu chí
class CriteriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Criteria
        fields = '__all__'


# Tiêu chí của khóa luận
class ThesisCriteriaSerializer(serializers.ModelSerializer):
    criteria = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()

    def get_criteria(self, obj):
        criteria_instance = obj.criteria
        serializer = CriteriaSerializer(criteria_instance)
        return serializer.data

    def get_scores(self, obj):
        scores_queryset = Score.objects.filter(thesis_criteria=obj)
        serializer = ScoreSerializer(scores_queryset, many=True)
        return serializer.data

    class Meta:
        model = ThesisCriteria
        fields = ['id', 'thesis', 'criteria', 'weight', 'scores']


# Bài đăng
class PostSerializer(serializers.ModelSerializer):
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['id', 'created_date', 'updated_date', 'content', 'user', 'like_count', 'comment_count']
        read_only_fields = ['user']

    def get_user(self, obj):
        user_id = obj.user_id
        user = User.objects.get(pk=user_id)
        user_serializer = UserSerializer(user)
        return user_serializer.data

    def get_like_count(self, obj):
        return obj.like_set.filter(active=True).count()

    def get_comment_count(self, obj):
        return obj.comment_set.count()


class AuthenticatedPost(PostSerializer):
    liked = serializers.SerializerMethodField()

    def get_liked(self, post):
        user = self.context['request'].user
        if user.is_authenticated:
            return post.like_set.filter(user=user, active=True).exists()
        return False

    class Meta:
        model = PostSerializer.Meta.model
        fields = PostSerializer.Meta.fields + ['liked']


# Bình luận
class CommentSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return UserSerializer(obj.user).data

    class Meta:
        model = Comment
        fields = ['id', 'content', 'created_date', 'user']


# Thống kê
class ThesisStatsSerializer(serializers.Serializer):
    start_year = serializers.IntegerField()
    end_year = serializers.IntegerField()
    avg_score = serializers.FloatField()


class MajorThesisCountSerializer(serializers.Serializer):
    major_name = serializers.CharField()
    thesis_count = serializers.IntegerField()
