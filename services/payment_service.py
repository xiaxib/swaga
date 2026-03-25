from dataclasses import dataclass


@dataclass
class PaymentResult:
    success: bool
    message: str


class PaymentService:
    """Абстракция для платежей. Для MVP можно подключить mock-реализацию."""

    def create_subscription_payment(self, user_id: int, amount_rub: int) -> PaymentResult:
        raise NotImplementedError


class MockPaymentService(PaymentService):
    """Заглушка оплаты: реальных списаний нет."""

    def create_subscription_payment(self, user_id: int, amount_rub: int) -> PaymentResult:
        return PaymentResult(
            success=True,
            message=(
                f"Тестовый платеж на {amount_rub} ₽ для пользователя {user_id} создан. "
                "Для MVP активируйте подписку через /admin_grant_sub."
            ),
        )
