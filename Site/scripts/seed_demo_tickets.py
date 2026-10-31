from datetime import UTC, datetime

from app.database import DEFAULT_DATABASE_PATH, TicketRepository


SYNTHETIC_TICKETS = (
    {
        "ticket_id": "DEMO-SYNTHETIC-T1",
        "player_id": "SYNTHETIC-DEMO-T1",
        "message": (
            "Прошу обжаловать бан за использование читов. Блокировку получил "
            "вчера около 18 часов; считаю решение ошибочным."
        ),
        "priority": "Normal",
    },
    {
        "ticket_id": "DEMO-SYNTHETIC-T2",
        "player_id": "SYNTHETIC-DEMO-T2",
        "message": (
            "Игрок SYNTHETIC-PLAYER-02 оскорблял меня в чате вчера около "
            "20 часов на сервере DEMO-1."
        ),
        "priority": "Normal",
    },
    {
        "ticket_id": "DEMO-SYNTHETIC-T3",
        "player_id": "SYNTHETIC-DEMO-T3",
        "message": (
            "Жалоба на администратора SYNTHETIC-ADMIN-03: он некорректно "
            "общался в чате вчера около 19 часов на сервере DEMO-1."
        ),
        "priority": "Normal",
    },
    {
        "ticket_id": "DEMO-SYNTHETIC-T4",
        "player_id": "SYNTHETIC-DEMO-T4",
        "message": (
            "Подозреваю взлом: после неизвестного входа потерял доступ к "
            "аккаунту. Пароль и коды доступа не отправляю."
        ),
        "priority": "Urgent",
    },
    {
        "ticket_id": "DEMO-SYNTHETIC-T5",
        "player_id": "SYNTHETIC-DEMO-T5",
        "message": (
            "Игрок SYNTHETIC-PLAYER-05, возможно, использует читы и получает "
            "преимущество на сервере DEMO-1."
        ),
        "priority": "High",
    },
    {
        "ticket_id": "DEMO-SYNTHETIC-T6",
        "player_id": "SYNTHETIC-DEMO-T6",
        "message": "Помогите разобраться, пожалуйста.",
        "priority": "Normal",
    },
)


def seed_demo_tickets(repository: TicketRepository) -> tuple[list[str], list[str]]:
    created: list[str] = []
    skipped: list[str] = []
    for item in SYNTHETIC_TICKETS:
        ticket_id = item["ticket_id"]
        if repository.get_ticket(ticket_id) is not None:
            skipped.append(ticket_id)
            continue
        repository.create_ticket(
            ticket_id=ticket_id,
            player_id=item["player_id"],
            message=item["message"],
            category=None,
            priority=item["priority"],
            created_at=datetime.now(UTC).isoformat(),
            attachments=[],
        )
        created.append(ticket_id)
    return created, skipped


def main() -> None:
    repository = TicketRepository(DEFAULT_DATABASE_PATH)
    created, skipped = seed_demo_tickets(repository)
    print(f"Created {len(created)} synthetic demo tickets: {', '.join(created) or 'none'}")
    print(f"Skipped {len(skipped)} existing demo tickets: {', '.join(skipped) or 'none'}")
    print("No official rules or real player data were added.")


if __name__ == "__main__":
    main()