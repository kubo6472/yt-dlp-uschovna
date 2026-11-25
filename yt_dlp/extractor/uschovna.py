import os

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    clean_html,
    get_element_by_class,
    get_elements_html_by_class,
    parse_filesize,
    urljoin,
)


class UschovnaIE(InfoExtractor):
    IE_NAME = 'uschovna'
    IE_DESC = 'Úschovna.cz shipments'

    # Page (/zasilka/), optional language prefix (/en/, /sk/), or a direct link.
    _VALID_URL = (
        r'https?://(?:www\d*\.)?uschovna\.cz/(?:(?:en|sk)/)?'
        r'(?P<kind>zasilka|download-zip|download)/(?P<id>[A-Za-z0-9]+-[A-Za-z0-9]+)'
    )

    _TESTS = [{
        'url': 'https://www.uschovna.cz/zasilka/XS24Z6M786CWXS32-DIK',
        'only_matching': True,  # real shipments expire and have download limits
    }]

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        package_id, kind = mobj.group('id'), mobj.group('kind')

        # The user pasted a link that was already generated: nothing to scrape.
        if kind != 'zasilka':
            return self._make_entry(
                package_id, url, title=package_id,
                ext='zip' if kind == 'download-zip' else 'bin', referer=url)

        webpage = self._download_webpage(url, package_id)

        # The sender's "message to recipient" makes a decent title.
        title = clean_html(get_element_by_class('message', webpage)) or package_id

        # "Download all as zip" is /download-zip/<pkg>/zip-<token>/ ; the token is
        # generated per page view, so it must be scraped fresh each time.
        zip_path = self._search_regex(
            r'href=(["\'])(?P<path>/download-zip/[^"\']+)\1',
            webpage, 'zip link', default=None, group='path')

        # Opt-in: one big zip instead of separate files.
        if self._configuration_arg('zip'):
            if not zip_path:
                raise ExtractorError('This shipment has no zip link', expected=True)
            return self._make_entry(
                package_id, urljoin(url, zip_path), title=title, ext='zip', referer=url)

        # Each file sits in a <div class="soubor"> block: a relative link
        # /download/<pkg>/<file-id>/ plus name (div.title) and size (div.size).
        # The links redirect to a numbered server (www201.uschovna.cz, ...).
        entries, seen = [], set()
        for block in get_elements_html_by_class('soubor', webpage):
            path = self._search_regex(
                r'href=(["\'])(?P<path>/download/[^"\']+)\1',
                block, 'file link', default=None, group='path')
            if not path or path in seen:  # each row has two <a> with the same href
                continue
            seen.add(path)

            file_id = path.rstrip('/').rsplit('/', 1)[-1]
            filename = clean_html(get_element_by_class('title', block)) or file_id
            stem, ext = os.path.splitext(filename)
            entries.append(self._make_entry(
                f'{package_id}_{file_id}', urljoin(url, path),
                title=stem or filename, ext=ext.lstrip('.').lower() or 'bin',
                referer=url,
                filesize_approx=parse_filesize(clean_html(get_element_by_class('size', block)))))

        # Shipments have a download counter ("zbývá N stažení"); each real
        # download uses one up, listing only loads the page.
        if not entries:
            raise ExtractorError(
                'No files found. The shipment may be expired, deleted or password '
                'protected. Run with --write-pages to see what yt-dlp received.',
                expected=True, video_id=package_id)
        if len(entries) == 1:
            return entries[0]
        return self.playlist_result(entries, package_id, title)

    @staticmethod
    def _make_entry(entry_id, url, *, title, ext, referer, **extra):
        # yt-dlp will happily download non-media files: it only needs a URL and
        # an extension to name the output. Redirects are followed automatically.
        return {
            'id': entry_id,
            'title': title,
            'url': url,
            'ext': ext,
            'http_headers': {'Referer': referer},
            **extra,
        }
