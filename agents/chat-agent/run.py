import asyncio
from agent import Chat_AgentAgent

async def main():
    agent = Chat_AgentAgent()
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main()) 