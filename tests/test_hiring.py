import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class Hiring(OfficeTest):
    def spec(self):
        return {'id':'reply-helper','name':'София','aliases':['Соня'],'role':'помощник по ответам на заявки','scope':['Черновики ответа по утверждённым сведениям'],'forbidden':['Отправлять сообщения','Выдумывать цены'],'need':'Повторяются локальные черновики ответов','sources':['team/agents/demiurg/templates/niche-helper.md'],'method':'Используй только подтверждённые факты и один ясный следующий шаг. Неизвестную цену не придумывай.','scenarios':['Составить ответ по заявке без отправки'],'tone':'По профилю владельца'}

    def test_draft_probe_confirmation_activation(self):
        from hire import create_employee, activate_employee
        from registry import load_registry
        from router import route
        create_employee(self.root,self.spec())
        item=next(a for a in load_registry(self.root)['agents'] if a['id']=='reply-helper')
        self.assertEqual(item['status'],'draft')
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',{'task':'','output':'','confirmed':True})
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',{'task':'Ответить на заявку','output':'Черновик ответа','confirmed':False})
        activate_employee(self.root,'reply-helper',{'task':'Ответить на заявку','output':'Здравствуйте. Уточните удобное время.','confirmed':True})
        self.assertEqual(route(self.root,'Соня, подготовь ответ')['agent']['status'],'active')
        card=(self.root/'team/agents/reply-helper/card.md').read_text()
        self.assertIn('me/profile.md',card)

    def test_no_method_no_fake_expert(self):
        from hire import create_employee
        spec=self.spec(); spec['sources']=[]
        with self.assertRaises(ValueError): create_employee(self.root,spec)

    def test_alias_collision_leaves_no_orphan(self):
        from hire import create_employee
        spec=self.spec(); spec['aliases']=['Никита']
        with self.assertRaises(ValueError): create_employee(self.root,spec)
        self.assertFalse((self.root/'team/agents/reply-helper').exists())

    def test_corrupted_placeholder_card_cannot_activate(self):
        from hire import create_employee, activate_employee
        create_employee(self.root,self.spec())
        path=self.root/'team/agents/reply-helper/card.md'
        path.write_text(path.read_text().replace('Повторяются локальные черновики ответов','<заполнить>'))
        with self.assertRaises(ValueError):
            activate_employee(self.root,'reply-helper',{'task':'Ответить на заявку','output':'Здравствуйте. Уточните время.','confirmed':True})
