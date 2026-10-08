import frappe
from frappe import _
from frappe.model.document import Document


class AIFormGroup(Document):
	def validate(self):
		if not self.parent_group:
			return
		seen = {self.name}
		parent = self.parent_group
		while parent:
			if parent in seen:
				frappe.throw(_("A group cannot be its own parent."))
			seen.add(parent)
			parent = frappe.db.get_value("AI Form Group", parent, "parent_group")
		parent_area = frappe.db.get_value("AI Form Group", self.parent_group, "target_area")
		if not self.target_area:
			self.target_area = parent_area
		elif parent_area and parent_area != self.target_area:
			frappe.throw(_("A subgroup must belong to the same area as its parent group."))
