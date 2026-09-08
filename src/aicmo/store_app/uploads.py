"""Bound incoming files before Django writes them to temporary storage."""

from collections.abc import Callable

from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import Resolver404, resolve
from django.views.decorators.cache import never_cache
from django.views.defaults import bad_request

from aicmo.outcomes import MAX_CSV_BYTES
from aicmo.photos import MAX_PHOTO_BYTES


def _csv_request(request: HttpRequest) -> bool:
    try:
        return resolve(request.path_info).url_name == "outcomes-preview"
    except Resolver404:
        return False


class PhotoUploadRejected(RequestDataTooBig):
    """An upload must fail as a whole instead of accepting its partial POST."""


class PhotoUploadHandler(TemporaryFileUploadHandler):
    def __init__(self, request: HttpRequest | None = None) -> None:
        super().__init__(request)
        self.max_file_bytes = (
            MAX_CSV_BYTES if request is not None and _csv_request(request) else MAX_PHOTO_BYTES
        )

    def receive_data_chunk(self, raw_data: bytes, start: int) -> None:
        if start + len(raw_data) > self.max_file_bytes:
            # Django's parser only closes completed files on this exception.
            self.file.close()
            reason = "Upload exceeded the file size limit."
            raise PhotoUploadRejected(reason)
        super().receive_data_chunk(raw_data, start)

    def upload_interrupted(self) -> None:
        super().upload_interrupted()
        reason = "Upload was interrupted."
        raise PhotoUploadRejected(reason)


class UploadCleanupMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        finally:
            if request.content_type == "multipart/form-data":
                for handler in request.upload_handlers:
                    if isinstance(handler, PhotoUploadHandler) and hasattr(handler, "file"):
                        # Views persist normalized bytes, never a response backed by this file.
                        handler.file.close()


@never_cache
def upload_bad_request(request: HttpRequest, exception: Exception) -> HttpResponse:
    if isinstance(exception, (PhotoUploadRejected, TooManyFilesSent)):
        notice = (
            "CSV 파일을 받지 못했습니다. "
            "UTF-8 또는 UTF-8 BOM CSV 파일 1개를 32 KiB 이하로 다시 선택해 주세요."
            if _csv_request(request)
            else "사진을 받지 못했습니다. "
            "JPEG/PNG 사진은 1장만, 20 MiB 이하로 다시 선택해 주세요."
        )
        return render(
            request,
            "store_app/error.html",
            {"notice": notice},
            status=400,
        )
    return bad_request(request, exception)
