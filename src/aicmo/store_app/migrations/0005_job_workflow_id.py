from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar = [("store_app", "0004_publicationreport")]

    operations: ClassVar = [
        migrations.AddField(
            model_name="job",
            name="workflow_id",
            field=models.CharField(
                choices=[
                    ("local-store-pack", "주간 실행팩"),
                    ("weekly-report", "주간 성과 보고서"),
                    ("local-pack-feedback", "문안 피드백 검토"),
                ],
                default="local-store-pack",
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="job",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    workflow_id__in=["local-store-pack", "weekly-report", "local-pack-feedback"]
                ),
                name="store_job_workflow",
            ),
        ),
    ]
