#hello
#hello2
print("hello")
from dotenv import load_dotenv
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

class DocumentGenerator:
    """LLM 기반 문서 생성기"""

    def __init__(
        self,
        llm_provider: str = "openai",
        openai_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None
    ):
        """
        DocumentGenerator 초기화

        Args:
            llm_provider: "openai" 또는 "gemini"
            openai_api_key: OpenAI API 키 (선택적)
            gemini_api_key: Gemini API 키 (선택적)
        """
        # .env 파일에서 환경변수 로드
        load_dotenv()

        self.llm_provider = llm_provider.lower()

        if self.llm_provider == "openai":
            # OpenAI LLM 초기화
            self.llm = ChatOpenAI(
                model_name="gpt-4o",  # 최신 LangChain에서는 model_name 사용
                temperature=0.1,
                openai_api_key=openai_api_key or os.getenv("OPENAI_API_KEY")
            )
        elif self.llm_provider == "gemini":
            # Gemini LLM 초기화
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0.1,
                google_api_key=gemini_api_key or os.getenv("GEMINI_API_KEY")
            )
        else:
            raise ValueError(
                f"지원하지 않는 LLM 제공자: {llm_provider}. 'openai' 또는 'gemini'를 사용하세요."
            )

        # 출력 파서
        self.parser = StrOutputParser()

        # 워크플로우 생성
        self.workflow = self._build_workflow()
