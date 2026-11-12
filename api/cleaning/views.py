"""POST a file to /api/clean/ and get the cleaned rows plus a report back."""
import hmac
import io
import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from cleaner import CleanConfig, clean, read_table, to_records


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_POST
def clean_view(request):
    key = settings.CLEANER_API_KEY
    if key and not hmac.compare_digest(request.headers.get("X-API-Key", ""), key):
        return _error("Invalid or missing X-API-Key header", 401)

    upload = request.FILES.get("file")
    if upload is None:
        return _error("Send the dataset as multipart form field 'file'")
    if upload.size > settings.CLEANER_MAX_UPLOAD_MB * 1024 * 1024:
        return _error(f"File is larger than {settings.CLEANER_MAX_UPLOAD_MB} MB", 413)

    try:
        raw_config = request.POST.get("config") or "{}"
        config = CleanConfig.from_dict(json.loads(raw_config))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _error(f"Bad config: {exc}")

    try:
        df, report = clean(read_table(upload.read(), name=upload.name), config)
    except ValueError as exc:
        return _error(str(exc))
    except Exception:  # unreadable or corrupt file
        return _error("Could not read the file. Check that it is a valid CSV, Excel or JSON file.")

    if request.GET.get("download") == "csv":
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="cleaned.csv"'
        response["X-Rows-In"] = str(report["rows_in"])
        response["X-Rows-Out"] = str(report["rows_out"])
        return response
    return JsonResponse({"report": report, "rows": to_records(df)})
