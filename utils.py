from typing import Dict, List


def extract_stock(info_item: Dict, source: str) -> int:
    stocks = info_item.get("stocks", {}).get("stocks", [])
    for stock in stocks:
        if stock.get("source", "").lower() == source:
            return stock.get("present", 0)
    return 0


PACKAGING_COST = 40
PROMOTION_RATE = 0.01


def compute_financials(product: Dict, packaging_override: float = None, promotion_override: float = None) -> Dict:
    """Считаем метрики по товару без хранения тяжёлых «сырцов» в результате."""

    info = product.get("info", {}) or {}
    price_block = product.get("price", {}) or {}
    offer_id = product.get("offer_id")

    price_data = price_block.get("price", {}) or {}
    price_value = float(price_data.get("price", 0)) if price_data.get("price") not in (None, "") else 0.0
    cost_value = float(price_data.get("net_price", 0)) if price_data.get("net_price") not in (None, "") else 0.0
    min_price_value = (
        float(price_data.get("min_price", price_value))
        if price_data.get("min_price") not in (None, "")
        else price_value
    )

    commissions = price_block.get("commissions", {}) or {}
    sales_percent_fbs = float(commissions.get("sales_percent_fbs", 0) or 0)

    info_commissions = info.get("commissions") or []
    fbs_commission_entry = next(
        (
            c
            for c in info_commissions
            if "FBS" in str(c.get("sale_schema", "")).upper()
        ),
        None,
    )
    commission_value = 0.0
    commission_percent_source = sales_percent_fbs
    if fbs_commission_entry:
        commission_value = float(fbs_commission_entry.get("value") or 0)
        if price_value:
            commission_percent_source = max(
                commission_percent_source,
                (commission_value / price_value) * 100 if price_value else 0,
            )
    if commission_value == 0 and commission_percent_source:
        commission_value = price_value * commission_percent_source / 100

    logistics_value = float(commissions.get("fbs_direct_flow_trans_min_amount", 0) or 0)
    delivery_cost = float(commissions.get("fbs_deliv_to_customer_amount", 0) or 0)
    processing_cost = float(commissions.get("fbs_first_mile_min_amount", 0) or 0)

    acquiring_percent = 1.9
    acquiring_value = float(price_block.get("acquiring", 0) or 0)
    if acquiring_value == 0:
        acquiring_value = price_value * acquiring_percent / 100

    promotion_value = price_value * (promotion_override if promotion_override is not None else PROMOTION_RATE)
    packaging_value = packaging_override if packaging_override is not None else PACKAGING_COST

    expenses_without_cost = (
        commission_value
        + logistics_value
        + acquiring_value
        + delivery_cost
        + processing_cost
        + promotion_value
        + packaging_value
    )
    revenue = price_value - expenses_without_cost
    margin = revenue - cost_value
    markup = ((revenue - cost_value) / cost_value * 100) if cost_value else 0

    return {
        "offer_id": offer_id,
        "product_id": info.get("id") or product.get("product_id") or product.get("sku"),
        "name": info.get("name", ""),
        "price": round(price_value, 2),
        "cost": round(cost_value, 2),
        "stock_fbo": extract_stock(info, "fbo"),
        "stock_fbs": extract_stock(info, "fbs"),
        "commission": round(commission_value, 2),
        "commission_percent_fbs": round(commission_percent_source, 4),
        "logistics": round(logistics_value, 2),
        "acquiring": round(acquiring_value, 2),
        "acquiring_percent": acquiring_percent,
        "delivery_cost": round(delivery_cost, 2),
        "processing_cost": round(processing_cost, 2),
        "promotion": round(promotion_value, 2),
        "packaging": round(packaging_value, 2),
        "min_price": round(min_price_value, 2),
        "revenue": round(revenue, 2),
        "margin": round(margin, 2),
        "markup": round(markup, 2),
    }


def prepare_table_data(
    products: List[Dict], packaging_override: float = None, promotion_override: float = None
) -> List[Dict]:
    if not products:
        return []

    # Если данные уже рассчитаны (нет блока info/price) либо price не словарь,
    # возвращаем как есть, чтобы не пытаться трактовать числовое поле как блок цен
    sample = products[0]
    price_block = sample.get("price")
    if ("info" not in sample and "price" not in sample) or not isinstance(price_block, dict):
        return products

    return [compute_financials(p, packaging_override, promotion_override) for p in products]
