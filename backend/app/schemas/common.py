from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PipelineSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
