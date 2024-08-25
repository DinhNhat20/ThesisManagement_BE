from django.contrib.auth.hashers import make_password
from rest_framework import viewsets, parsers, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from theses import serializers, perms, paginators
from theses.models import User, Student, Position, CouncilDetail, Thesis, Lecturer, Criteria, ThesisCriteria, Score
from theses.signals import update_total_score


# Người dùng
class UserViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer
    parser_classes = [parsers.MultiPartParser, ]

    def get_permissions(self):
        if self.action in ['current_user']:
            return [perms.IsAuthenticated()]

        return [permissions.AllowAny()]

    # Lấy thông tin User đang chứng thực, cập nhật thông tin User
    @action(methods=['get', 'patch'], url_path='current-user', detail=False)
    def current_user(self, request):
        user = request.user
        if request.method.__eq__('PATCH'):
            data = request.data.copy()  # Tạo một bản sao của dữ liệu để tránh ảnh hưởng đến dữ liệu gốc
            if 'password' in data:
                data['password'] = make_password(data['password'])  # Băm mật khẩu

            serializer = serializers.UserSerializer(instance=user, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.UserSerializer(user).data)


# Giảng viên
class LecturerViewSet(viewsets.ViewSet, generics.ListCreateAPIView, generics.RetrieveAPIView):
    queryset = Lecturer.objects.all()
    serializer_class = serializers.LecturerSerializer
    pagination_class = paginators.BasePaginator
    parser_classes = [parsers.MultiPartParser]

    def get_queryset(self):
        queryset = self.queryset

        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(full_name__icontains=q)

        fac_id = self.request.query_params.get('faculty_id')
        if fac_id:
            queryset = queryset.filter(faculty_id=fac_id)

        return queryset

    # Lấy hội đồng giảng viên tham gia
    @action(detail=True, methods=['get'], url_path='councils')
    def get_councils(self, request, pk=None):
        lecturer = self.get_object()
        council_details = CouncilDetail.objects.filter(lecturer=lecturer).select_related('council', 'position')
        serializer = serializers.CouncilDetailWithIDSerializer(council_details, many=True)
        return Response(serializer.data)

    # Lấy khóa luận giảng viên hướng dẫn
    @action(detail=True, methods=['get'])
    def theses(self, request, pk=None):
        lecturer = self.get_object()
        theses = Thesis.objects.filter(lecturers=lecturer)
        serializer = serializers.ThesisSerializer(theses, many=True)
        return Response(serializer.data)

    # Lấy khóa luận giảng viên phản biện
    @action(detail=True, methods=['get'])
    def theses_review(self, request, pk=None):
        lecturer = self.get_object()
        review_positions = Position.objects.filter(name__icontains='Phản biện')
        council_details = (CouncilDetail.objects.filter(lecturer=lecturer, position__in=review_positions)
                           .select_related('council'))
        council_ids = council_details.values_list('council_id', flat=True)
        theses = (Thesis.objects.filter(council_id__in=council_ids).select_related('major', 'school_year', 'council')
                  .prefetch_related('lecturers'))
        serializer = serializers.ThesisSerializer(theses, many=True)
        return Response(serializer.data)


class StudentViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = Student.objects.all()
    serializer_class = serializers.StudentSerializer
    pagination_class = paginators.BasePaginator
    parser_classes = [parsers.MultiPartParser, ]

    def get_queryset(self):
        queryset = self.queryset

        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(full_name__icontains=q)

        maj_id = self.request.query_params.get('major_id')
        if maj_id:
            queryset = queryset.filter(major_id=maj_id)

        return queryset


class ScoreViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = Score.objects.all()
    serializer_class = serializers.ScoreSerializer
    parser_classes = [parsers.MultiPartParser]

    def get_permissions(self):
        if self.action in ['create']:
            return [perms.IsAuthenticated()]
        if self.action in ['update']:
            return [perms.ScoreOwner()]
        return [permissions.AllowAny()]

    def create(self, request):
        user = request.user

        thesis_criteria_id = request.data.get('thesis_criteria')
        score_number = request.data.get('score_number')

        if thesis_criteria_id is None or score_number is None:
            return Response({"Thông báo": "Tiêu chí khóa luận và điểm không được bỏ trống!"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            thesis_criteria_id = int(thesis_criteria_id)
        except ValueError:
            return Response({"Thông báo": "ID của tiêu chí phải là số nguyên!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            thesis_criteria = ThesisCriteria.objects.get(id=thesis_criteria_id)
        except ThesisCriteria.DoesNotExist:
            return Response({"Thông báo": "Tiêu chí khóa luận không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)

        if not hasattr(user, 'lecturer'):
            return Response({"Thông báo": "Bạn không phải là giảng viên!"}, status=status.HTTP_403_FORBIDDEN)

        council_detail = CouncilDetail.objects.filter(lecturer=user.lecturer,
                                                      council=thesis_criteria.thesis.council).first()
        if not council_detail:
            return Response({"Thông báo": "Bạn không phải là thành viên của hội đồng chấm khóa luận này!"},
                            status=status.HTTP_403_FORBIDDEN)

        if thesis_criteria.thesis.council.is_lock:
            return Response({"Thông báo": "Hội đồng đã bị khóa và không thể chấm hay chỉnh sửa điểm!"},
                            status=status.HTTP_403_FORBIDDEN)

        if not (0 <= float(score_number) <= 10):
            return Response({"Thông báo": "Điểm phải nằm trong khoảng từ 0 đến 10!"},
                            status=status.HTTP_400_BAD_REQUEST)

        existing_score = Score.objects.filter(thesis_criteria=thesis_criteria, council_detail=council_detail).first()
        if existing_score:
            return Response({"Thông báo": "Bạn đã chấm điểm cho tiêu chí này rồi!"}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            'thesis_criteria': thesis_criteria_id,
            'council_detail': council_detail.id,
            'score_number': score_number
        }

        serializer = serializers.ScoreSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        user = request.user

        # Extract and validate data from request
        score_number = request.data.get('score_number')

        if score_number is None:
            return Response({"Thông báo": "Điểm không được bỏ trống!"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            score = Score.objects.get(id=pk)
        except Score.DoesNotExist:
            return Response({"Thông báo": "Điểm không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)

        if score.council_detail.lecturer.user != user:
            return Response({"Thông báo": "Bạn không có quyền chỉnh sửa điểm này!"}, status=status.HTTP_403_FORBIDDEN)

        if score.thesis_criteria.thesis.council.is_lock:
            return Response({"Thông báo": "Hội đồng đã bị khóa và không thể chấm hay chỉnh sửa điểm!"},
                            status=status.HTTP_403_FORBIDDEN)

        if not (0 <= float(score_number) <= 10):
            return Response({"Thông báo": "Điểm phải nằm trong khoảng từ 0 đến 10!"},
                            status=status.HTTP_400_BAD_REQUEST)

        score.score_number = score_number
        score.save()

        serializer = serializers.ScoreSerializer(score, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# Tiêu chí
class CriteriaViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.ListAPIView, generics.DestroyAPIView):
    queryset = Criteria.objects.all()
    serializer_class = serializers.CriteriaSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.BasePaginator


# Tiêu chí của khóa luận
class ThesisCriteriaViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = ThesisCriteria.objects.all()
    serializer_class = serializers.ThesisCriteriaSerializer
    parser_classes = [parsers.MultiPartParser]

    @action(detail=False, methods=['post'], url_path='add')
    def add_criteria(self, request):
        thesis_code = request.data.get('thesis')
        criteria_id = request.data.get('criteria')
        weight = request.data.get('weight')
        print(thesis_code)

        if float(weight) < 0 or float(weight) > 1:
            return Response({'Thông báo': 'Tỉ lệ phải từ 0 -> 1 (0 -> 100%)!'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            thesis = Thesis.objects.get(code=thesis_code)
        except Thesis.DoesNotExist:
            return Response({'Thông báo': 'Không tìm thấy khóa luận!'}, status=status.HTTP_404_NOT_FOUND)

        total_weight = sum(criteria.weight for criteria in thesis.thesiscriteria_set.all())
        if float(total_weight) + float(weight) > 1:
            return Response({'Thông báo': 'Tổng tỉ lệ phải bằng 1 (100%)!'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            criteria = Criteria.objects.get(id=criteria_id)
        except Criteria.DoesNotExist:
            return Response({'Thông báo': 'Không tìm thấy tiêu chí!'}, status=status.HTTP_404_NOT_FOUND)

        if ThesisCriteria.objects.filter(thesis=thesis, criteria=criteria).exists():
            return Response({'Thông báo': 'Tiêu chí này đã được gán cho khóa luận!'},
                            status=status.HTTP_400_BAD_REQUEST)

        thesis_criteria = ThesisCriteria(thesis=thesis, criteria=criteria, weight=weight)
        thesis_criteria.save()

        serializer = self.serializer_class(thesis_criteria)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# Khóa luận
class ThesisViewSet(viewsets.ViewSet, generics.ListCreateAPIView, generics.RetrieveAPIView, generics.DestroyAPIView):
    queryset = Thesis.objects.prefetch_related('lecturers').all().order_by('code')
    serializer_class = serializers.ThesisSerializer
    parser_classes = [parsers.MultiPartParser, ]
    pagination_class = paginators.ThesisPaginator

    def get_queryset(self):
        queryset = self.queryset

        # Lọc theo các tham số truy vấn
        q = self.request.query_params.get('q')
        council_id = self.request.query_params.get('council_id')
        major_id = self.request.query_params.get('major_id')
        school_year_id = self.request.query_params.get('school_year_id')

        if q:
            queryset = queryset.filter(name__icontains=q)
        if council_id:
            queryset = queryset.filter(council_id=council_id)
        if major_id:
            queryset = queryset.filter(major_id=major_id)
        if school_year_id:
            queryset = queryset.filter(school_year_id=school_year_id)

        return queryset

    # Sửa thông tin
    def partial_update(self, request, pk=None):
        thesis = self.get_object()
        serializer = self.serializer_class(thesis, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            update_total_score(thesis.code)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Thêm giảng viên hướng dẫn vào khóa luận
    @action(detail=True, methods=['post'], url_path='add_lecturer')
    def add_lecturer(self, request, pk=None):
        try:
            thesis = self.get_object()

            if thesis.lecturers.count() >= 2:
                return Response({"Thông báo": "Khóa luận đã đủ hai giảng viên hướng dẫn không thể thêm!"}, status=status.HTTP_400_BAD_REQUEST)

            lecturer_code = request.data.get('lecturer_code')

            lecturer = Lecturer.objects.get(code=lecturer_code)
        except (Thesis.DoesNotExist, Lecturer.DoesNotExist):
            return Response({"Thông báo": "Khóa luận hoặc giảng viên không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)

        if lecturer in thesis.lecturers.all():
            return Response({"Thông báo": "Giảng viên đã có trong danh sách hướng dẫn!"}, status=status.HTTP_400_BAD_REQUEST)

        thesis.lecturers.add(lecturer)
        thesis.save()

        serializer = self.get_serializer(thesis)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Thêm khóa luận vào trong sinh viên
    @action(detail=True, methods=['post'], url_path='add_student')
    def add_student(self, request, pk=None):
        try:
            thesis = self.get_object()
            student_id = request.data.get('student_id')
            student = Student.objects.get(user_id=student_id)
        except (Thesis.DoesNotExist, Student.DoesNotExist):
            return Response({"Thông báo": "Khóa luận hoặc sinh viên không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)

        if student.thesis:
            return Response({"Thông báo": "Sinh viên đã có khóa luận!"}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra ngành của sinh viên phải cùng với ngành của khóa luận
        if student.major != thesis.major:
            return Response({'Thông báo': 'Không thể thêm do sinh viên và khóa luận không cùng ngành!'},
                            status=status.HTTP_400_BAD_REQUEST)

        student.thesis = thesis
        student.save()

        serializer = self.get_serializer(thesis)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Lấy tiêu chí của KL
    @action(detail=True, methods=['get'], url_path='criteria')
    def get_thesis_criteria(self, request, pk=None):
        try:
            thesis = Thesis.objects.prefetch_related('thesiscriteria_set__criteria').get(pk=pk)
            thesis_criteria = thesis.thesiscriteria_set.all()
            serializer = serializers.ThesisCriteriaSerializer(thesis_criteria, many=True)
            return Response(serializer.data)
        except Thesis.DoesNotExist:
            return Response({"Thông báo": "Không tìm thấy khóa luận!"}, status=status.HTTP_404_NOT_FOUND)

    # Lấy điểm giảng viên chấm cho KL
    @action(detail=True, methods=['get'], url_path='lecturer-scores')
    def get_lecturer_scores(self, request, pk=None):
        try:
            lecturer = request.user.lecturer
        except Lecturer.DoesNotExist:
            return Response({"Thông báo": "Không tìm thấy giảng viên!"}, status=status.HTTP_404_NOT_FOUND)

        try:
            thesis = self.get_object()
        except Thesis.DoesNotExist:
            return Response({"Thông báo": "Không tìm thấy khóa luận!"}, status=status.HTTP_404_NOT_FOUND)

        council_details = thesis.council.councildetail_set.filter(lecturer=lecturer)
        scores = Score.objects.filter(thesis_criteria__thesis=thesis, council_detail__in=council_details)

        response_data = []
        for score in scores:
            response_data.append({
                'id': score.id,
                'thesis_criteria': score.thesis_criteria.id,
                'council_detail': score.council_detail.id,
                'score_number': score.score_number,
                'criteria_name': score.thesis_criteria.criteria.name,
                'evaluation_method': score.thesis_criteria.criteria.evaluation_method
            })

        return Response(response_data, status=status.HTTP_200_OK)