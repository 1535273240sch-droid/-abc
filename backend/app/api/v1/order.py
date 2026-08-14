from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_audit_service, get_order_service
from app.schemas.order import OrderIntentRequest, OrderResponse
from app.services.audit_service import AuditService
from app.services.order_service import OrderService

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


@router.post("/intents", response_model=OrderResponse)
async def create_order_intent(
    body: OrderIntentRequest,
    request: Request,
    order_service: OrderService = Depends(get_order_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    order = order_service.create_intent(
        client_order_id=body.client_order_id,
        account_id=body.account_id,
        strategy_id=body.strategy_id,
        strategy_version=body.strategy_version,
        symbol=body.symbol,
        market_type=body.market_type,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        limit_price=body.limit_price,
        mode=body.mode,
        risk_decision_id=body.risk_decision_id,
    )

    audit_service.record(
        event_type="order.created",
        actor=body.account_id,
        resource_type="order",
        resource_id=order.client_order_id,
        details={
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "status": order.status.value,
            "risk_decision_id": order.risk_decision_id,
        },
        ip_address=request.client.host if request.client else None,
        trace_id=getattr(request.state, "request_id", None),
    )

    return OrderResponse(
        client_order_id=order.client_order_id,
        account_id=order.account_id,
        strategy_id=order.strategy_id,
        strategy_version=order.strategy_version,
        symbol=order.symbol,
        market_type=order.market_type.value,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        limit_price=order.limit_price,
        mode=order.mode.value,
        risk_decision_id=order.risk_decision_id,
        status=order.status.value,
        filled_quantity=order.filled_quantity,
        average_price=order.average_price,
        reject_reason=order.reject_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    account_id: str | None = Query(None),
    order_service: OrderService = Depends(get_order_service),
):
    orders = order_service.get_orders(account_id=account_id)
    return [
        OrderResponse(
            client_order_id=o.client_order_id,
            account_id=o.account_id,
            strategy_id=o.strategy_id,
            strategy_version=o.strategy_version,
            symbol=o.symbol,
            market_type=o.market_type.value,
            side=o.side.value,
            order_type=o.order_type.value,
            quantity=o.quantity,
            limit_price=o.limit_price,
            mode=o.mode.value,
            risk_decision_id=o.risk_decision_id,
            status=o.status.value,
            filled_quantity=o.filled_quantity,
            average_price=o.average_price,
            reject_reason=o.reject_reason,
            created_at=o.created_at,
            updated_at=o.updated_at,
        )
        for o in orders
    ]