"""Слой Domain: BehavioralModel и результат проверки.

Ни LLM, ни БД, ни subprocess — только схемы и их проверки. Всё, что пересекает границу
LLM / Model Checker, проходит через модели этого пакета: на вход `BehavioralModel`,
на выход `VerificationResult`, а рядом с ним агрегат `Verification`, к которому
присоединено объяснение агента.
"""
