"""python -m analyst.cli "What was net revenue by region last quarter?" """
import sys

from analyst import agent
from analyst.config import load_env, model_name
from analyst.llm import OpenAIModel


def main() -> None:
    load_env()
    if len(sys.argv) < 2:
        sys.exit('usage: python -m analyst.cli "your question"')
    a = agent.ask(" ".join(sys.argv[1:]), OpenAIModel(model_name()))
    print(f"[{a.status}] {a.message}")
    if a.sql:
        print("\n" + a.sql + "\n")
    if a.rows:
        print(" | ".join(a.columns))
        for row in a.rows[:20]:
            print(" | ".join(str(v) for v in row))
    print(f"\n{a.attempts} attempt(s), {a.seconds}s, {a.input_tokens} in / {a.output_tokens} out tokens")


if __name__ == "__main__":
    main()
