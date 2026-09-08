"""Bound incoming photo files before Django writes them to temporary storage."""

from collections.abc import Callable

from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.defaults import bad_request

from aicmo.photos import MAX_PHOTO_BYTES


class PhotoUploadRejected(RequestDataTooBig):
    """An upload must fail as a whole instead of accepting its partial POST."""


class PhotoUploadHandler(TemporaryFileUploadHandler):
    def receive_data_chunk(self, raw_data: bytes, start: int) -> None:
        if start + len(raw_data) > MAX_PHOTO_BYTES:
            # Django's parser only closes completed files on this exception.
            self.file.close()
            reason = "Photo upload exceeded the file size limit."
            raise PhotoUploadRejected(reason)
        super().receive_data_chunk(raw_data, start)

    def upload_interrupted(self) -> None:
        super().upload_interrupted()
        reason = "Photo upload was interrupted."
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
        return render(
            request,
            "store_app/error.html",
            {
                "notice": "사진을 받지 못했습니다. "
                "JPEG/PNG 사진은 1장만, 20 MiB 이하로 다시 선택해 주세요."
            },
            status=400,
        )
    return bad_request(request, exception)
