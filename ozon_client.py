import logging
import time
from typing import Dict, List, Optional
import requests


class OzonClientError(Exception):
    pass


class OzonClient:
    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, client_id: str, api_key: str):
        self.headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict, *, timeout: int = 240) -> dict:
        """Безопасный POST с несколькими попытками.

        При больших выгрузках запросы к Ozon могут кратковременно падать по таймауту
        или отдавать 5xx. Увеличили таймаут и число попыток, чтобы снизить вероятность
        обрыва задачи по единичной сетевой ошибке.
        """

        url = f"{self.BASE_URL}{path}"
        last_error: Optional[str] = None
        for attempt in range(5):
            try:
                response = requests.post(
                    url, json=payload, headers=self.headers, timeout=timeout
                )
                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        last_error = "Невалидный JSON в ответе"
                        logging.error("Ozon API returned invalid JSON for %s", path)
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    logging.error("Ozon API error %s: %s", response.status_code, response.text)
            except requests.RequestException as exc:  # сеть или таймаут
                last_error = str(exc)
                logging.error("Ozon API request failure: %s", exc)

            # backoff с увеличением
            time.sleep(1 + attempt)

        raise OzonClientError(f"Ошибка запроса {path}: {last_error or 'неизвестная ошибка'}")

    def list_products(self, limit: int = 100, last_id: str = "") -> dict:
        payload = {"filter": {"visibility": "ALL"}, "last_id": last_id, "limit": limit}
        return self._post("/v3/product/list", payload)

    def product_info(self, offer_ids: List[str]) -> dict:
        payload = {"offer_id": offer_ids}
        return self._post("/v3/product/info/list", payload)

    def product_prices(self, offer_ids: List[str], limit: int = 100, cursor: str = "") -> dict:
        payload = {
            "cursor": cursor,
            "filter": {"offer_id": offer_ids, "visibility": "ALL"},
            "limit": limit,
        }
        return self._post("/v5/product/info/prices", payload)

    def average_delivery_time(self) -> dict:
        return self._post("/v1/analytics/average-delivery-time/summary", {})

    def import_prices(self, prices: List[Dict]) -> dict:
        payload = {"prices": prices}
        return self._post("/v1/product/import/prices", payload)

    def list_actions(self) -> dict:
        """Запрос списка акций выполняется методом GET (по спецификации).

        Ранее использовался POST, из-за чего сервер возвращал 405 и срывал
        загрузку страницы акций/заказов. Оставляем единый обработчик ошибок
        и увеличенный таймаут.
        """

        url = f"{self.BASE_URL}/v1/actions"
        last_error: Optional[str] = None
        for attempt in range(5):
            try:
                response = requests.get(url, headers=self.headers, timeout=240)
                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        last_error = "Невалидный JSON в ответе"
                        logging.error("Ozon API returned invalid JSON for %s", url)
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    logging.error("Ozon API error %s: %s", response.status_code, response.text)
            except requests.RequestException as exc:
                last_error = str(exc)
                logging.error("Ozon API request failure: %s", exc)
            time.sleep(1 + attempt)
        raise OzonClientError(f"Ошибка запроса /v1/actions: {last_error or 'неизвестная ошибка'}")

    def action_candidates(self, action_id: int, limit: int = 100, offset: int = 0, last_id: str = "") -> dict:
        payload = {
            "action_id": action_id,
            "limit": limit,
            "offset": offset,
            "last_id": last_id,
        }
        return self._post("/v1/actions/candidates", payload)

    def action_products(self, action_id: int, limit: int = 100, offset: int = 0, last_id: str = "") -> dict:
        payload = {
            "action_id": action_id,
            "limit": limit,
            "offset": offset,
            "last_id": last_id,
        }
        return self._post("/v1/actions/products", payload)

    def activate_action_products(self, action_id: int, products: List[Dict]) -> dict:
        payload = {"action_id": action_id, "products": products}
        return self._post("/v1/actions/products/activate", payload)

    def deactivate_action_products(self, action_id: int, product_ids: List[int]) -> dict:
        payload = {"action_id": action_id, "product_ids": product_ids}
        return self._post("/v1/actions/products/deactivate", payload)

    def list_fbs_postings(self, since: str, to: str, limit: int = 100, offset: int = 0) -> dict:
        payload = {
            "dir": "ASC",
            "filter": {
                "since": since,
                "to": to,
                "warehouse_id": [],
            },
            "limit": limit,
            "offset": offset,
            "with": {
                "analytics_data": True,
                "barcodes": True,
                "financial_data": True,
                "translit": True,
            },
        }
        return self._post("/v3/posting/fbs/list", payload, timeout=25)

    def list_fbo_postings(self, since: str, to: str, limit: int = 100, offset: int = 0) -> dict:
        payload = {
            "dir": "ASC",
            "filter": {
                "since": since,
                "to": to,
                "status": "",
            },
            "limit": limit,
            "offset": offset,
            "translit": True,
            "with": {
                "analytics_data": True,
                "financial_data": True,
                "legal_info": False,
            },
        }
        return self._post("/v2/posting/fbo/list", payload, timeout=25)

    def get_fbo_posting(self, posting_number: str) -> dict:
        payload = {
            "posting_number": posting_number,
            "translit": True,
            "with": {"analytics_data": True, "financial_data": True, "legal_info": False},
        }
        return self._post("/v2/posting/fbo/get", payload)

    def get_fbs_posting(self, posting_number: str) -> dict:
        payload = {
            "posting_number": posting_number,
            "with": {
                "analytics_data": True,
                "barcodes": True,
                "financial_data": True,
                "legal_info": True,
                "product_exemplars": True,
                "related_postings": True,
                "translit": True,
            },
        }
        return self._post("/v3/posting/fbs/get", payload)

    def fetch_postings(self, since: str, to: str) -> List[Dict]:
        all_postings: List[Dict] = []

        # FBS postings
        offset = 0
        limit = 100
        while True:
            fbs_resp = self.list_fbs_postings(since, to, limit=limit, offset=offset)
            postings = fbs_resp.get("result", {}).get("postings", [])
            for item in postings:
                item["scheme"] = "FBS"
            all_postings.extend(postings)
            has_next = fbs_resp.get("result", {}).get("has_next", False)
            if not has_next or not postings:
                break
            offset += limit

        # FBO postings
        offset = 0
        limit = 200
        while True:
            fbo_resp = self.list_fbo_postings(since, to, limit=limit, offset=offset)
            postings = fbo_resp.get("result", [])
            for item in postings:
                item["scheme"] = "FBO"
            if not postings:
                break
            all_postings.extend(postings)
            if len(postings) < limit:
                break
            offset += limit

        # Не вызываем детализацию для каждой отгрузки, чтобы не получать таймауты.
        # Списки уже содержат financial_data, analytics и товары, поэтому возвращаем их как есть.
        enriched: List[Dict] = []
        for posting in all_postings:
            scheme = posting.get("scheme") or ""
            posting.setdefault("scheme", scheme)
            enriched.append(posting)

        return enriched

    def _fetch_all_products(self, page_limit: int = 1000) -> List[Dict]:
        items: List[Dict] = []
        last_id = ""
        while True:
            resp = self.list_products(limit=page_limit, last_id=last_id)
            page_items = resp.get("result", {}).get("items", [])
            items.extend(page_items)
            last_id = resp.get("result", {}).get("last_id") or ""
            if not last_id or not page_items:
                break
        return items

    def _chunked(self, seq: List[str], size: int = 1000):
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def fetch_joined_products(self) -> List[Dict]:
        products = self._fetch_all_products()
        offer_ids = [item.get("offer_id") for item in products if item.get("offer_id")]
        if not offer_ids:
            return []

        info_map: Dict[str, Dict] = {}
        for chunk in self._chunked(offer_ids, 1000):
            info_resp = self.product_info(chunk)
            for item in info_resp.get("items", []):
                info_map[item.get("offer_id")] = item

        price_map: Dict[str, Dict] = {}
        for chunk in self._chunked(offer_ids, 1000):
            cursor = ""
            while True:
                price_resp = self.product_prices(chunk, limit=1000, cursor=cursor)
                for item in price_resp.get("items", []):
                    price_map[item.get("offer_id")] = item
                cursor = price_resp.get("cursor") or ""
                if not cursor:
                    break

        avg_delivery = None
        try:
            avg_delivery = self.average_delivery_time()
        except Exception:
            avg_delivery = None

        combined = []
        for offer_id in offer_ids:
            combined.append({
                "offer_id": offer_id,
                "info": info_map.get(offer_id, {}),
                "price": price_map.get(offer_id, {}),
                "delivery": avg_delivery or {},
            })
        return combined
