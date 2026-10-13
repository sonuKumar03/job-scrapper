"""Small offline check: rtk uv run python tools/check_scraper_diagnostics.py."""

from job_scrapper.connectors.base import BaseConnector


def main() -> None:
    empty = {**BaseConnector.new_stats(), 'listing_pages': 1}
    BaseConnector.finalize_diagnostics(empty)
    assert 'empty' in empty['warnings'][0]
    invalid = {**BaseConnector.new_stats(), 'found': 2, 'detail_invalid': 2, 'detail_valid': 0}
    BaseConnector.finalize_diagnostics(invalid)
    assert 'parser' in invalid['warnings'][0]
    for extra in ({}, {'found': 4, 'inserted': 0, 'listing_pages': 1},
                  {'found': 4, 'detail_invalid': 0, 'detail_valid': 0},
                  {'found': 4, 'detail_invalid': 1, 'detail_valid': 1}):
        stats = {**BaseConnector.new_stats(), **extra}
        BaseConnector.finalize_diagnostics(stats)
        assert not stats.get('warnings'), stats
    print('Diagnostic assertions passed.')


if __name__ == '__main__':
    main()
