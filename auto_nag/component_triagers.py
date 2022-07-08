# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from libmozdata.bugzilla import BugzillaProduct

from auto_nag.round_robin import RoundRobin

# Component names will be formed as tuple of (PRODUCT, COMPONENT)
ComponentName = Tuple[str, str]


@dataclass
class TriageOwner:
    product: str
    component: str
    bugzilla_email: str

    def get_pc(self) -> tuple:
        """Get the product component name"""
        return (self.product, self.component)

    def get_pc_str(self) -> str:
        """Get the string representation of product component name"""
        return f"{self.product}::{self.component}"


class ComponentTriagers:
    def __init__(
        self,
        excluded_components: List[ComponentName] = [],
        excluded_teams: List[str] = [],
    ) -> None:
        """Constructor

        Args:
            excluded_components: list of components to excluded
            excluded_teams: list of teams to exclude all of their components
        """
        self.round_robin: RoundRobin = RoundRobin.get_instance()
        self.triagers: Dict[tuple, str] = {}
        products = [pc.split("::", 1)[0] for pc in self.round_robin.get_components()]
        self._fetch_triagers(products, set(excluded_components), set(excluded_teams))

    def _fetch_triagers(
        self,
        products: List[str],
        excluded_components: Set[ComponentName],
        excluded_teams: Set[str],
    ) -> None:
        def handler(product, data):
            data.update(
                {
                    (product["name"], component["name"]): component["triage_owner"]
                    for component in product["components"]
                    if component["team_name"] not in excluded_teams
                    and (product["name"], component["name"]) not in excluded_components
                }
            )

        BugzillaProduct(
            product_names=products,
            include_fields=[
                "name",
                "components.name",
                "components.team_name",
                "components.triage_owner",
            ],
            product_handler=handler,
            product_data=self.triagers,
        ).wait()

    def get_rotation_triage_owners(self, product: str, component: str) -> list:
        """Get the triage owner in the rotation.

        Args:
            product: the name of the product.
            component: the name of the component.

        Returns:
            List of bugzilla emails for people defined to be triage owners as
            today based on the rotations source. If component does not have a
            rotation source, an empty list will be returned.
        """
        calendar = self.round_robin.get_component_calendar(product, component)
        if not calendar:
            return []

        return [email for name, email in calendar.get_persons("today")]

    def get_current_triage_owner(self, product: str, component: str) -> str:
        """Get the current triage owner as defined on Bugzilla.

        Args:
            product: the name of the product.
            component: the name of the component.

        Returns:
            The bugzilla email of the triage owner.
        """

        return self.triagers[(product, component)]

    def get_new_triage_owners(self) -> List[TriageOwner]:
        """Get the triage owners that are different than what are defined on
        Bugzilla.

        Returns:
            The new triage owner based on the rotation source (i.e., calendar).
            If the rotation source returns more than one person, the first one
            will be selected as the new triage owner.
        """
        triagers = []
        for (product, components), current_triager in self.triagers.items():
            new_triagers = self.get_rotation_triage_owners(product, components)
            if new_triagers and not any(
                new_triager == current_triager for new_triager in new_triagers
            ):
                triagers.append(TriageOwner(product, components, new_triagers[0]))

        return triagers
