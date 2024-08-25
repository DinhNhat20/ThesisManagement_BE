from decimal import Decimal, ROUND_HALF_UP

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Score, Thesis, ThesisCriteria


def update_total_score(thesis_code):
    try:
        thesis = Thesis.objects.get(code=thesis_code)
        thesis_criteria = ThesisCriteria.objects.filter(thesis=thesis)

        if thesis_criteria.exists():
            lecturer_total_scores = {}

            # Tính tổng điểm có trọng số của từng giảng viên
            for criteria in thesis_criteria:
                scores = Score.objects.filter(thesis_criteria=criteria)
                for score in scores:
                    lecturer_id = score.council_detail.lecturer.pk
                    weighted_score = score.score_number * criteria.weight

                    if lecturer_id not in lecturer_total_scores:
                        lecturer_total_scores[lecturer_id] = Decimal(weighted_score)
                    else:
                        lecturer_total_scores[lecturer_id] += Decimal(weighted_score)

            total_scores = list(lecturer_total_scores.values())  # Danh sách các tổng điểm của từng giảng viên

            # Tính trung bình cộng của tất cả các giảng viên
            overall_average_score = sum(total_scores) / len(total_scores) if total_scores else Decimal('0.00')
            overall_average_score = overall_average_score.quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)

            # Cập nhật vào khóa luận
            thesis.total_score = float(overall_average_score)  # Convert về float để lưu vào FloatField
            thesis.result = overall_average_score >= Decimal('5.00')
            thesis.save()
        else:
            thesis.total_score = 0.00
            thesis.result = False
            thesis.save()
    except Thesis.DoesNotExist:
        print("Lỗi khi tính điểm")


@receiver(post_save, sender=Score)
def score_saved(sender, instance, **kwargs):
    update_total_score(instance.thesis_criteria.thesis.code)


@receiver(post_delete, sender=Score)
def score_deleted(sender, instance, **kwargs):
    update_total_score(instance.thesis_criteria.thesis.code)