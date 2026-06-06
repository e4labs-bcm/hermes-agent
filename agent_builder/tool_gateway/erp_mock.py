"""Read-only mock ERP functions for the Agent Builder MVP."""

from __future__ import annotations


_CUSTOMERS = {
    "ACME": {
        "id": "cust_acme",
        "name": "ACME",
        "segment": "enterprise",
        "status": "active",
    }
}

_ORDERS = [
    {"id": "ord_001", "customer_id": "cust_acme", "status": "open", "total": 12500.0},
    {"id": "ord_002", "customer_id": "cust_acme", "status": "closed", "total": 8700.0},
    {"id": "ord_003", "customer_id": "cust_acme", "status": "open", "total": 4200.0},
]


def erp_get_customer(customer_name: str) -> dict:
    customer = _CUSTOMERS.get(customer_name.upper())
    if customer is None:
        return {"customer": None, "matches": []}
    return {"customer": dict(customer), "matches": [dict(customer)]}


def erp_list_orders(customer_id: str, status: str = "open") -> dict:
    orders = [
        dict(order)
        for order in _ORDERS
        if order["customer_id"] == customer_id and order["status"] == status
    ]
    return {"customer_id": customer_id, "status": status, "orders": orders}
