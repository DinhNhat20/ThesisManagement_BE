import os
from io import BytesIO
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.db.models import Avg, Count, F
from django.db.models.functions import ExtractYear
from django.http import Http404, HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from rest_framework import viewsets, generics, status, parsers, permissions
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from theses.models import *
from theses import serializers, paginators, perms
from django.core.mail import EmailMessage
from django.conf import settings
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
                return Response({"Thông báo": "Khóa luận đã đủ hai giảng viên hướng dẫn không thể thêm!"},
                                status=status.HTTP_400_BAD_REQUEST)

            lecturer_code = request.data.get('lecturer_code')

            lecturer = Lecturer.objects.get(code=lecturer_code)
        except (Thesis.DoesNotExist, Lecturer.DoesNotExist):
            return Response({"Thông báo": "Khóa luận hoặc giảng viên không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)

        if lecturer in thesis.lecturers.all():
            return Response({"Thông báo": "Giảng viên đã có trong danh sách hướng dẫn!"},
                            status=status.HTTP_400_BAD_REQUEST)

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

        # Xuất bản điểm ra file PDF

    @action(detail=True, methods=['get'], url_path='generate-pdf')
    def generate_pdf(self, request, pk=None, colors=None):
        thesis = get_object_or_404(Thesis, pk=pk)

        total_score = thesis.total_score
        major_name = thesis.major.name
        students = thesis.student_set.all()
        instructors = thesis.lecturers.all()
        council_name = thesis.council.name

        lecturer_total_scores = {}
        for thesis_criteria in thesis.thesiscriteria_set.all():
            scores = Score.objects.filter(thesis_criteria=thesis_criteria)
            for score in scores:
                lecturer_id = score.council_detail.lecturer.pk
                weighted_score = score.score_number * thesis_criteria.weight
                position = score.council_detail.position  # Lấy chức vụ của giảng viên

                if lecturer_id not in lecturer_total_scores:
                    lecturer_total_scores[lecturer_id] = {
                        'lecturer': score.council_detail.lecturer.full_name,
                        'score': weighted_score,
                        'position': position  # Lưu chức vụ
                    }
                else:
                    lecturer_total_scores[lecturer_id]['score'] += weighted_score

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="score_sheet_{thesis.code}.pdf"'

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = letter

        font_path = os.path.join(os.path.dirname(__file__), 'static/fonts/tahoma.ttf')
        pdfmetrics.registerFont(TTFont('Tahoma', font_path))

        pdf.setFont("Tahoma", 12)

        text_width = pdf.stringWidth("BỘ GIÁO DỤC VÀ ĐẠO TẠO", "Tahoma", 12)
        text_height = 800

        pdf.drawString((350 - text_width) / 2, text_height, "BỘ GIÁO DỤC VÀ ĐẠO TẠO")

        text_width = pdf.stringWidth("TRƯỜNG ĐẠI HỌC MỞ TP. HỒ CHÍ MINH", "Tahoma", 12)

        pdf.drawString((350 - text_width) / 2, text_height - 20, "TRƯỜNG ĐẠI HỌC MỞ TP. HỒ CHÍ MINH")

        title = f"PHIẾU CHẤM ĐIỂM"
        title_width = pdf.stringWidth(title, "Tahoma", 12)
        pdf.drawString(500 - title_width, 800, title)

        y_position = 740

        pdf.setFont("Tahoma", 14)

        thesis_title = f"ĐỀ TÀI: {thesis.name}"
        thesis_title_width = pdf.stringWidth(thesis_title, "Tahoma", 12)

        pdf.drawString((letter[0] - thesis_title_width) / 2 - 35, letter[1] - 50, thesis_title)

        lecturer_total_scores = {}
        for thesis_criteria in thesis.thesiscriteria_set.all():
            scores = Score.objects.filter(thesis_criteria=thesis_criteria)
            for score in scores:
                lecturer_id = score.council_detail.lecturer.pk
                weighted_score = score.score_number * thesis_criteria.weight
                position = score.council_detail.position.name if score.council_detail.position else ''

                if lecturer_id not in lecturer_total_scores:
                    lecturer_total_scores[lecturer_id] = {
                        'lecturer': score.council_detail.lecturer.full_name,
                        'score': weighted_score,
                        'position': position,
                    }
                else:
                    lecturer_total_scores[lecturer_id]['score'] += weighted_score

        pdf.drawString(50, page_height - 100, f"Ngành: {major_name}")

        pdf.drawString(50, page_height - 130, "Danh sách sinh viên thực hiện:")
        student_start_y = page_height - 160
        for student in students:
            pdf.drawString(60, student_start_y, f"Mã SV: {student.code}")
            pdf.drawString(170, student_start_y, f"Tên: {student.full_name}")
            pdf.drawString(340, student_start_y, f"Ngành: {student.major.name}")
            student_start_y -= 30

        pdf.drawString(50, page_height - 250, "Danh sách giảng viên hướng dẫn:")
        counselor_start_y = page_height - 280
        for instructor in instructors:
            pdf.drawString(60, counselor_start_y, f"Mã GV: {instructor.code}")
            pdf.drawString(170, counselor_start_y, f"Tên: {instructor.full_name}")
            counselor_start_y -= 30

        pdf.drawString(50, page_height - 370, f"Hội đồng chấm khóa luận: {council_name}")

        # Vẽ bảng điểm
        pdf.setFont("Tahoma", 12)
        data = [['TÊN GIẢNG VIÊN', 'CHỨC VỤ', 'ĐIỂM']]
        for lecturer_id, info in lecturer_total_scores.items():
            data.append([info['lecturer'], info['position'], f"{info['score']}"])

        data.append(['', 'TỔNG ĐIỂM', f"{total_score}"])

        col_widths = [page_width * 0.4, page_width * 0.2, page_width * 0.2]  # Cập nhật độ rộng các cột
        row_height = 20
        table_width = sum(col_widths)

        table = Table(data, colWidths=col_widths, rowHeights=row_height)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Tahoma'),  # Đặt font Tahoma cho toàn bộ bảng
            ('FONTSIZE', (0, 0), (-1, -1), 12),  # Đặt kích thước font
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
        ]))

        table.wrapOn(pdf, table_width, 400)

        table_x = 50
        table_y = page_height - 500

        table.drawOn(pdf, table_x, table_y)

        pdf.setFont("Tahoma", 12)
        date_string = f"TP. Hồ Chí Minh, Ngày......Tháng......Năm......"
        signature_string = "Chữ ký lãnh đạo (Ký và ghi rõ họ tên)"
        date_string_width = pdf.stringWidth(date_string, "Tahoma", 12)
        signature_string_width = pdf.stringWidth(signature_string, "Tahoma", 12)

        margin = 50

        max_string_width = max(date_string_width, signature_string_width)
        start_x = pdf._pagesize[0] - max_string_width - margin
        date_y = margin + 180
        signature_y = margin + 160

        pdf.drawString(start_x, date_y, date_string)
        pdf.drawString(start_x + 15, signature_y, signature_string)

        pdf.save()

        buffer.seek(0)
        pdf_data = buffer.read()

        if not pdf_data.startswith(b'%PDF'):
            return Response({'Thông báo': 'Xuất file PDF thất bại!'}, status=500)

        buffer.close()

        filename = f"score_{thesis.code}.pdf"
        file_path = default_storage.save(os.path.join('media', filename), ContentFile(pdf_data))
        file_url = default_storage.url(file_path)

        return Response({'file_url': request.build_absolute_uri(file_url)})


# Thống kê
class ThesisStatsViewSet(viewsets.ViewSet):
    permission_classes = [perms.IsMinistry]

    def list(self, request):
        avg_score_by_school_year = Thesis.objects.values(
            'school_year__start_year', 'school_year__end_year'
        ).annotate(
            start_year=ExtractYear('school_year__start_year'),
            end_year=ExtractYear('school_year__end_year'),
            avg_score=Avg('total_score')
        )

        for item in avg_score_by_school_year:
            if item['avg_score'] is not None:
                item['avg_score'] = round(item['avg_score'], 2)

        thesis_major_count = Major.objects.annotate(
            major_name=F('name'),
            thesis_count=Count('thesis')
        )

        avg_score_serializer = serializers.ThesisStatsSerializer(avg_score_by_school_year, many=True)
        thesis_count_serializer = serializers.MajorThesisCountSerializer(thesis_major_count, many=True)

        return Response({
            'avg_score_by_school_year': avg_score_serializer.data,
            'thesis_major_count': thesis_count_serializer.data
        })

# Hội đồng
class CouncilViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.ListAPIView, generics.DestroyAPIView):
    queryset = Council.objects.all()
    serializer_class = serializers.CouncilSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.BasePaginator

    def get_queryset(self):
        queryset = self.queryset

        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(name__icontains=q)

        status = self.request.query_params.get('is_lock')
        if status:
            queryset = queryset.filter(is_lock=status)

        return queryset

    # Sửa thông tin hội đồng
    def partial_update(self, request, pk=None):
        council = self.get_object()
        serializer = self.serializer_class(council, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Cập nhật trường is_lock của Council
    @action(methods=['post'], url_path='update_lock', detail=True)
    def update_lock(self, request, pk=None):
        council = self.get_object()
        old_lock_status = council.is_lock
        council.is_lock = not council.is_lock
        council.save()

        if not old_lock_status and council.is_lock:
            for council_detail in council.councildetail_set.all():
                for student in council_detail.lecturer.thesis_set.first().student_set.all():
                    self.send_score_notification_email(student, council_detail.lecturer.thesis_set.first().total_score)

        return Response({'is_lock': council.is_lock}, status=status.HTTP_200_OK)

    def send_score_notification_email(self, student, total_score):
        student_email = student.user.email
        subject = 'Thông báo điểm khóa luận'
        message = (
            f'Điểm của khóa luận "{student.thesis.name}" đã được chấm.\n'
            f'Khóa luận của sinh viên "{student.full_name}" được "{total_score}" điểm.\n'
            'Mọi thắc mắc vui lòng liên hệ hội đồng trong vòng 3 - 5 ngày kể từ ngày nhận thông báo.\n'
            '__Giáo vụ__'
        )

        from_email = 'Thesis Management <{}>'.format(settings.DEFAULT_FROM_EMAIL)
        email = EmailMessage(subject, message, from_email, to=[student_email])
        email.send()

    # Lấy danh sách thành viên trong hội đồng
    @action(detail=True, methods=['get'], url_path='members')
    def get_members(self, request, pk=None):
        try:
            council = self.get_object()
            members = CouncilDetail.objects.filter(council=council).select_related('lecturer', 'position')
            members_data = [{
                "id": member.id,
                "lecturer_id": member.lecturer.user_id,
                "full_name": member.lecturer.full_name,
                "position": member.position.name
            } for member in members]
            return Response(members_data, status=status.HTTP_200_OK)
        except Council.DoesNotExist:
            return Response({'Thông báo': 'Không tìm thấy hội đồng!'}, status=status.HTTP_404_NOT_FOUND)

    # Lấy danh sách khóa luận hội đồng chấm
    @action(methods=['get'], url_path='theses', detail=True)
    def get_theses(self, request, pk=None):
        try:
            council = self.queryset.get(pk=pk)
            theses = council.thesis_set.all()
            serializer = serializers.ThesisSerializer(theses, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Council.DoesNotExist:
            return Response({'Thông báo': 'Không tìm thấy hội đồng!'}, status=status.HTTP_404_NOT_FOUND)

    # Gán hội đồng vào khóa luận
    @action(detail=True, methods=['post'], url_path='assign-thesis')
    def assign_thesis(self, request, pk=None):
        try:
            council = self.get_object()
        except Council.DoesNotExist:
            return Response({'Thông báo': 'Hội đồng không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

        if council.thesis_set.count() >= 5:
            return Response({'Thông báo': 'Một hội đồng chỉ chấm tối đa 5 khóa luận!'},
                            status=status.HTTP_400_BAD_REQUEST)

        thesis_code = request.data.get('thesis_code')
        try:
            thesis = Thesis.objects.get(code=thesis_code)
        except Thesis.DoesNotExist:
            return Response({'Thông báo': 'Khóa luận không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

        if thesis.council:
            return Response({'Thông báo': f'Khóa luận {thesis_code} đã được gán hội đồng!'},
                            status=status.HTTP_400_BAD_REQUEST)

        thesis_lecturers = thesis.lecturers.all()
        council_lecturers = council.councildetail_set.values_list('lecturer', flat=True)
        if any(lecturer.user_id in council_lecturers for lecturer in thesis_lecturers):
            return Response({'Thông báo': 'Hội đồng có giảng viên là giảng viên hướng dẫn khóa luận này!'},
                            status=status.HTTP_400_BAD_REQUEST)

        thesis.council = council
        thesis.save()

        return Response(serializers.CouncilSerializer(council).data, status=status.HTTP_201_CREATED)


# Chi tiết hội đồng
class CouncilDetailViewSet(viewsets.ViewSet, generics.DestroyAPIView):
    queryset = CouncilDetail.objects.all()
    serializer_class = serializers.CouncilDetailSerializer
    parser_classes = [parsers.MultiPartParser]

    # Gửi email gán GVPB
    def send_reviewer_email(self, council, lecturer):
        lecturer_email = lecturer.user.email
        lecturer_name = lecturer.full_name
        council_name = council.name
        subject = f'Bạn đã được giao làm phản biện cho hội đồng "{council_name}"'
        message = (
            f'Chào {lecturer_name}\nBạn đã được giao vai trò phản biện cho hội đồng "{council_name}".\n'
            'Vui lòng chuẩn bị và liên hệ với các thành viên khác trong hội đồng để hoàn thành nhiệm vụ của mình.\n'
            '__Giáo vụ__'
        )

        from_email = 'Thesis Management <{}>'.format(settings.DEFAULT_FROM_EMAIL)

        email = EmailMessage(subject, message, from_email, to=[lecturer_email])
        email.send()

    # Thêm, sửa thành viên hội đồng
    @action(detail=False, methods=['post', 'patch'], url_path='members')
    def member_manager(self, request):
        council_id = request.data.get('council')
        lecturer_id = request.data.get('lecturer')
        position_id = request.data.get('position')

        try:
            council = Council.objects.prefetch_related('councildetail_set').get(id=council_id)
        except Council.DoesNotExist:
            return Response({'Thông báo': 'Hội đồng không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

        council_details = council.councildetail_set.all()

        if council_details.count() >= 5:
            return Response({'Thông báo': 'Một hội đồng chỉ có tối đa năm thành viên!'}, status=status.HTTP_400_BAD_REQUEST)

        # Đếm số lượng từng vị trí bằng ID
        position_counts = {
            1: 0,  # ID của chủ tịch
            2: 0,  # ID của thư ký
            3: 0  # ID của phản biện
        }

        for detail in council_details:
            pos_id = detail.position.id
            if pos_id in position_counts:
                position_counts[pos_id] += 1

        try:
            position = Position.objects.get(id=position_id)
        except Position.DoesNotExist:
            return Response({'Thông báo': 'Vị trí không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

        # Kiểm tra vị trí bằng ID
        if position.id == 1 and position_counts[1] >= 1:
            return Response({'Thông báo': 'Hội đồng chỉ có một chủ tịch!'}, status=status.HTTP_400_BAD_REQUEST)
        if position.id == 2 and position_counts[2] >= 1:
            return Response({'Thông báo': 'Hội đồng chỉ có một thư ký!'}, status=status.HTTP_400_BAD_REQUEST)
        if position.id == 3 and position_counts[3] >= 1:
            return Response({'Thông báo': 'Hội đồng chỉ có một phản biện!'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lecturer = Lecturer.objects.get(user_id=lecturer_id)
        except Lecturer.DoesNotExist:
            return Response({'Thông báo': 'Giảng viên không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

        # Kiểm tra nếu giảng viên đã có một chức vụ trong hội đồng này
        if council_details.filter(lecturer_id=lecturer_id).exists():
            return Response({'Thông báo': 'Giảng viên này đã giữ một chức vụ khác trong hội đồng!'},
                            status=status.HTTP_400_BAD_REQUEST)

        if request.method.__eq__('POST'):
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                council_detail = serializer.save()

                # Gửi email nếu là phản biện
                if position.id == 3:
                    self.send_reviewer_email(council, lecturer)

                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if request.method.__eq__('PATCH'):
            try:
                council_detail = CouncilDetail.objects.get(council_id=council_id, lecturer_id=lecturer_id)
            except CouncilDetail.DoesNotExist:
                return Response({'Thông báo': 'Thành viên hội đồng không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

            try:
                position = Position.objects.get(id=position_id)
            except Position.DoesNotExist:
                return Response({'Thông báo': 'Vị trí không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)

            council_detail.position = position
            council_detail.save()

            if position.id == 3:
                council = Council.objects.get(id=council_id)
                lecturer = Lecturer.objects.get(user_id=lecturer_id)
                self.send_reviewer_email(council, lecturer)

            return Response({'Thông báo': 'Thông tin vị trí đã được cập nhật!'}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except Http404:
            return Response({'Thông báo': 'Thành viên hội đồng không tồn tại!'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'Thông báo': str(e)}, status=status.HTTP_400_BAD_REQUEST)
# Bài đăng
class PostViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
    queryset = Post.objects.filter(active=True).order_by('-created_date')
    serializer_class = serializers.PostSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.PostCommentPaginator

    def get_queryset(self):
        queryset = self.queryset
        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(content__icontains=q)

        return queryset

    def get_permissions(self):
        if self.action in ['create', 'add_comment', 'like']:
            return [permissions.IsAuthenticated()]
        if self.action in ['partial_update', 'destroy']:
            return [perms.PostOwner()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.user.is_authenticated:
            return serializers.AuthenticatedPost

        return self.serializer_class

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Sửa post
    def partial_update(self, request, pk=None):
        post = self.get_object()
        serializer = self.serializer_class(post, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Xóa post
    def destroy(self, request, pk=None):
        post = self.get_object()
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['get'], url_path='comments', detail=True)
    def get_comments(self, request, pk):
        comments = self.get_object().comment_set.select_related('user').order_by('-id')

        paginator = paginators.BasePaginator()
        page = paginator.paginate_queryset(comments, request)
        if page is not None:
            serializer = serializers.CommentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        return Response(serializers.CommentSerializer(comments, many=True).data)

    @action(methods=['post'], url_path='comment', detail=True)
    def add_comment(self, request, pk):
        c = self.get_object().comment_set.create(content=request.data.get('content'),
                                                 user=request.user)
        return Response(serializers.CommentSerializer(c).data, status=status.HTTP_201_CREATED)

    @action(methods=['post'], url_path='like', detail=True)
    def like(self, request, pk):
        post = self.get_object()
        li, created = Like.objects.get_or_create(post=self.get_object(),
                                                 user=request.user)
        if not created:
            li.active = not li.active
            li.save()

        context = {'request': request}
        serializer = serializers.AuthenticatedPost(post, context=context)
        return Response(serializer.data, status=status.HTTP_200_OK)
        # return Response(serializers.AuthenticatedPost(self.get_object()).data)


# Bình luận
class CommentViewSet(viewsets.ViewSet, generics.DestroyAPIView):
    queryset = Comment.objects.filter(active=True).order_by('-created_date')
    serializer_class = serializers.CommentSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.PostCommentPaginator
    permission_classes = [perms.CommentOwner]

    # Sửa comment
    def partial_update(self, request, pk=None):
        cmt = self.get_object()
        serializer = self.serializer_class(cmt, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)