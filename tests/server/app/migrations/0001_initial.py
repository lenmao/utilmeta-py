# Generated by Django 4.2.1 on 2023-12-18 14:31

from django.db import migrations, models
import django.db.models.deletion
import utilmeta.core.orm.backends.django.models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BaseContent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public", models.BooleanField(default=False)),
                ("type", models.CharField(default="article", max_length=20)),
            ],
            options={
                "db_table": "content",
                "ordering": ["-created_at", "-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="Follow",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("follow_time", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "follow",
            },
        ),
        migrations.CreateModel(
            name="Article",
            fields=[
                (
                    "basecontent_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="app.basecontent",
                    ),
                ),
                ("title", models.CharField(max_length=40)),
                ("description", models.TextField(default="")),
                ("slug", models.SlugField(unique=True)),
                ("views", models.PositiveIntegerField(default=0)),
                ("tags", models.JSONField(default=list)),
            ],
            options={
                "db_table": "article",
            },
            bases=("app.basecontent",),
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.CharField(max_length=20, unique=True)),
                (
                    "password",
                    utilmeta.core.orm.backends.django.models.PasswordField(
                        max_length=20, min_length=6, regex=None, salt_length=32
                    ),
                ),
                ("jwt_token", models.TextField(default=None, null=True)),
                (
                    "avatar",
                    models.FileField(default=None, null=True, upload_to="image/avatar"),
                ),
                ("admin", models.BooleanField(default=False)),
                ("signup_time", models.DateTimeField(auto_now_add=True)),
                (
                    "followers",
                    models.ManyToManyField(
                        related_name="followings", through="app.Follow", to="app.user"
                    ),
                ),
            ],
            options={
                "db_table": "user",
            },
        ),
        migrations.AddField(
            model_name="follow",
            name="target",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_followers",
                to="app.user",
            ),
        ),
        migrations.AddField(
            model_name="follow",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_followings",
                to="app.user",
            ),
        ),
        migrations.AddField(
            model_name="basecontent",
            name="author",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contents",
                to="app.user",
            ),
        ),
        migrations.AddField(
            model_name="basecontent",
            name="liked_bys",
            field=models.ManyToManyField(
                db_table="like", related_name="likes", to="app.user"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="follow",
            unique_together={("user", "target")},
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                (
                    "basecontent_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="app.basecontent",
                    ),
                ),
                (
                    "on_content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="app.basecontent",
                    ),
                ),
            ],
            options={
                "db_table": "comment",
            },
            bases=("app.basecontent",),
        ),
    ]
