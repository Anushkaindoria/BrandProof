from app.seed import seed_database


if __name__ == "__main__":
    print(f"Seeded organization id={seed_database(reset=True)}")
