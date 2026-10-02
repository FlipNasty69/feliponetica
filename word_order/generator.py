from abc import ABC, abstractmethod


class ChallengeGenerator(ABC):
    @abstractmethod
    def challenge_ids(self, connection, level_id):
        """Return playable challenge IDs for a level."""


class AuthoredChallengeGenerator(ChallengeGenerator):
    def challenge_ids(self, connection, level_id):
        rows = connection.execute("""
            SELECT challenges.challenge_id
            FROM challenges
            JOIN patterns ON patterns.pattern_id = challenges.pattern_id
            WHERE challenges.level_id = ?
                AND challenges.active = 1
                AND patterns.min_level <= challenges.level_id
            ORDER BY challenges.challenge_id
        """, (level_id,)).fetchall()
        return [row["challenge_id"] for row in rows]