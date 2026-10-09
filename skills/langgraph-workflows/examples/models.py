"""The chat model: an Azure OpenAI deployment on Azure's v1 API."""

from langchain_openai import ChatOpenAI


def chat_model(endpoint: str, api_key: str, deployment: str) -> ChatOpenAI:
    """Plain `ChatOpenAI` on the v1 endpoint: no `AzureChatOpenAI`, no `api_version`."""
    return ChatOpenAI(
        base_url=f"{endpoint.rstrip('/')}/openai/v1/",
        api_key=api_key,
        model=deployment,
        use_responses_api=True,
    )
