from __future__ import annotations

import asyncio
import getpass
import json
from pathlib import Path

from app.core.config import Settings
from app.domain.models import AgentContext, UserSession
from app.infrastructure.clients.food_client import FoodClient


OUTPUT_FILE = Path(r"D:\serviceAi\food_real_data_sample.json")


async def main() -> None:
    settings = Settings(_env_file=r"D:\serviceAi\.env")

    default_employee_id = str(
        getattr(settings, "default_employee_id", "") or ""
    ).strip()

    employee_id = input(
        f"Employee ID [{default_employee_id}]: "
    ).strip() or default_employee_id

    if not employee_id:
        print("Employee ID is required.")
        return

    token = getpass.getpass(
        "Authorization Token (hidden): "
    ).strip()

    if not token:
        print("Authorization Token is required.")
        return

    session = UserSession(
        authorization_token=token,
    )

    initial_context = AgentContext(
        employee_id=employee_id,
        session=session,
    )

    client = FoodClient(settings)

    try:
        print("Reading allowed restaurants...")

        restaurants_payload = await client.get_my_restaurants(
            initial_context
        )

        restaurants = (
            restaurants_payload.get("data", [])
            if isinstance(restaurants_payload, dict)
            else []
        )

        print("\nAllowed restaurants:")

        if isinstance(restaurants, list):
            for restaurant in restaurants:
                if not isinstance(restaurant, dict):
                    continue

                print(
                    f"- {restaurant.get('value')}: "
                    f"{restaurant.get('text')}"
                )

        default_restaurant_id = str(
            getattr(settings, "default_restaurant_id", "") or ""
        ).strip()

        restaurant_id_text = input(
            f"\nRestaurant ID [{default_restaurant_id}]: "
        ).strip() or default_restaurant_id

        restaurant_id = (
            int(restaurant_id_text)
            if restaurant_id_text.isdigit()
            else None
        )

        default_meal_id = str(
            getattr(settings, "default_meal_id", "") or "1"
        ).strip()

        meal_id_text = input(
            f"Meal ID [{default_meal_id}]: "
        ).strip() or default_meal_id

        meal_id = (
            int(meal_id_text)
            if meal_id_text.isdigit()
            else 1
        )

        context = AgentContext(
            employee_id=employee_id,
            restaurant_id=restaurant_id,
            meal_id=meal_id,
            session=session,
        )

        print("\nReading real food history and menu...")

        history_payload, menu_payload = await asyncio.gather(
            client.get_my_food_reserve(context),
            client.get_food_plans_for_reserve(context),
        )

        result = {
            "employeeId": employee_id,
            "restaurantId": restaurant_id,
            "mealId": meal_id,
            "restaurants": restaurants_payload,
            "history": history_payload,
            "menu": menu_payload,
        }

        OUTPUT_FILE.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        print("\nSUCCESS")
        print(f"Output saved to: {OUTPUT_FILE}")

    except Exception as exc:
        print("\nFAILED")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error: {exc}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())