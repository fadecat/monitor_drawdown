from tickflow import TickFlow


def main() -> None:
    client = TickFlow(base_url="https://free-api.tickflow.org", timeout=10)
    try:
        df = client.klines.get("600000.SH", period="1d", count=100, as_dataframe=True)
        print(df.tail())

        instruments = client.instruments.batch(symbols=["600000.SH", "000001.SZ"])
        print(instruments)
    finally:
        client.close()


if __name__ == "__main__":
    main()
