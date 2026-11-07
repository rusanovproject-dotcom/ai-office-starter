import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/office'))
from helpers import OfficeTest

class Hiring(OfficeTest):
    def spec(self):
        self.put('knowledge/reply-method.md', '# Ответ на заявку\n\nИспользуй утверждённые факты; если цена неизвестна, предложи уточнить её у владельца. Не отправляй черновик.\n')
        return {'id':'reply-helper','name':'София','aliases':['Соня'],'role':'помощник по ответам на заявки','scope':['Черновики ответа по утверждённым сведениям'],'forbidden':['Отправлять сообщения','Выдумывать цены'],'need':'Повторяются локальные черновики ответов','sources':['knowledge/reply-method.md'],'method':'Используй только подтверждённые факты и один ясный следующий шаг. Неизвестную цену не придумывай.','scenarios':['Составить ответ по заявке без отправки'],'tone':'По профилю владельца'}

    def evidence(self):
        self.put('results/reply-probe.md', 'Здравствуйте. Уточните удобное время.\n')
        return {'task':'Ответить на заявку','output':'Подготовлен черновик без выдуманной цены','artifact':'results/reply-probe.md','criterion':'Нет неподтверждённой цены; есть следующий шаг; ничего не отправлено','assessment':'Цена не указана, запрошено удобное время, отправки не было','confirmed':True}

    def test_draft_probe_confirmation_activation(self):
        from hire import create_employee, activate_employee
        from registry import load_registry
        from router import route
        create_employee(self.root,self.spec())
        item=next(a for a in load_registry(self.root)['agents'] if a['id']=='reply-helper')
        self.assertEqual(item['status'],'draft')
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',{'task':'','output':'','confirmed':True})
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',{'task':'Ответить на заявку','output':'Черновик ответа','confirmed':False})
        activate_employee(self.root,'reply-helper',self.evidence())
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
            activate_employee(self.root,'reply-helper',self.evidence())

    def test_template_cannot_be_only_competence_source(self):
        from hire import create_employee
        spec=self.spec(); spec['sources']=['team/agents/demiurg/templates/niche-helper.md']
        with self.assertRaises(ValueError): create_employee(self.root,spec)
        self.assertFalse((self.root/'team/agents/reply-helper').exists())

    def test_artifact_criterion_assessment_required_before_activation(self):
        from hire import create_employee, activate_employee
        from registry import load_registry
        create_employee(self.root,self.spec())
        for missing in ('artifact','criterion','assessment'):
            with self.subTest(missing=missing):
                evidence=self.evidence(); evidence.pop(missing)
                with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',evidence)
        item=next(a for a in load_registry(self.root)['agents'] if a['id']=='reply-helper')
        self.assertEqual(item['status'],'draft')

    def test_artifact_must_exist_and_contain_a_result(self):
        from hire import create_employee, activate_employee
        create_employee(self.root,self.spec())
        for path, content in (('results/missing.md',None),('results/empty.md','  '),('results/placeholder.md','# Проба\n\n<заполнить>\n')):
            with self.subTest(path=path):
                if content is not None: self.put(path,content)
                evidence=self.evidence(); evidence['artifact']=path
                with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',evidence)

    def test_expert_needs_independent_domain_review(self):
        from hire import create_employee, activate_employee
        spec=self.spec(); spec['competence']='expert'; spec['role']='эксперт по локальным ответам'
        create_employee(self.root,spec)
        evidence=self.evidence()
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',evidence)
        self.put('results/domain-review.md', 'Проверены достоверность фактов и следующий шаг: критерий выполнен.\n')
        evidence['domain_review']={'reviewer':'София','verdict':'pass','artifact':'results/domain-review.md'}
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',evidence)
        evidence['domain_review']['reviewer']='Независимый доменный проверяющий'
        activate_employee(self.root,'reply-helper',evidence)
        card=(self.root/'team/agents/reply-helper/card.md').read_text()
        self.assertIn('Независимый доменный проверяющий',card)
        self.assertIn('results/domain-review.md',card)

    def test_local_role_cannot_claim_expert_competence(self):
        from hire import create_employee
        spec=self.spec(); spec['role']='эксперт по ответам'; spec['competence']='local'
        with self.assertRaises(ValueError): create_employee(self.root,spec)

    def test_source_still_required_at_activation(self):
        from hire import create_employee, activate_employee
        create_employee(self.root,self.spec())
        (self.root/'knowledge/reply-method.md').unlink()
        with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',self.evidence())

    def test_moved_template_is_not_a_competence_source(self):
        from hire import create_employee
        self.put('knowledge/copied-template.md',(self.root/'team/agents/demiurg/templates/niche-helper.md').read_text())
        spec=self.spec(); spec['sources']=['knowledge/copied-template.md']
        with self.assertRaises(ValueError): create_employee(self.root,spec)

    def test_placeholder_only_source_is_not_a_method(self):
        from hire import create_employee
        self.put('knowledge/pending.md','# Методика\n\nTODO pending\n')
        spec=self.spec(); spec['sources']=['knowledge/pending.md']
        with self.assertRaises(ValueError): create_employee(self.root,spec)

    def test_source_and_office_instructions_cannot_be_probe_artifacts(self):
        from hire import create_employee, activate_employee
        spec=self.spec()
        self.put('results/source-method.md','Используй утверждённые факты и не отправляй сообщения.\n')
        spec['sources']=['results/source-method.md']
        create_employee(self.root,spec)
        for path in ('AGENTS.md','results/AGENTS.md','results/source-method.md','team/agents/reply-helper/core.md'):
            with self.subTest(path=path):
                evidence=self.evidence(); evidence['artifact']=path
                with self.assertRaises(ValueError): activate_employee(self.root,'reply-helper',evidence)
