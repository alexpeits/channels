from __future__ import unicode_literals

import json

from django.contrib.auth import get_user_model

from channels import Group, route
from channels.binding.base import CREATE, DELETE, UPDATE
from channels.binding.websockets import WebsocketBinding
from channels.generic.websockets import WebsocketDemultiplexer
from channels.signals import consumer_finished
from channels.tests import ChannelTestCase, HttpClient, apply_routes

User = get_user_model()


class TestsBinding(ChannelTestCase):

    def test_trigger_outbound_create(self):

        class TestBinding(WebsocketBinding):
            model = User
            stream = 'test'
            fields = ['username', 'email', 'password', 'last_name']

            @classmethod
            def group_names(cls, instance, action):
                return ["users"]

            def has_permission(self, user, action, pk):
                return True

        client = HttpClient()
        client.join_group('users')

        user = User.objects.create(username='test', email='test@test.com')

        consumer_finished.send(sender=None)
        received = client.receive()
        self.assertTrue('payload' in received)
        self.assertTrue('action' in received['payload'])
        self.assertTrue('data' in received['payload'])
        self.assertTrue('username' in received['payload']['data'])
        self.assertTrue('email' in received['payload']['data'])
        self.assertTrue('password' in received['payload']['data'])
        self.assertTrue('last_name' in received['payload']['data'])
        self.assertTrue('model' in received['payload'])
        self.assertTrue('pk' in received['payload'])

        self.assertEqual(received['payload']['action'], 'create')
        self.assertEqual(received['payload']['model'], 'auth.user')
        self.assertEqual(received['payload']['pk'], user.pk)

        self.assertEqual(received['payload']['data']['email'], 'test@test.com')
        self.assertEqual(received['payload']['data']['username'], 'test')
        self.assertEqual(received['payload']['data']['password'], '')
        self.assertEqual(received['payload']['data']['last_name'], '')

        received = client.receive()
        self.assertIsNone(received)

    def test_trigger_outbound_create_exclude(self):
        class TestBinding(WebsocketBinding):
            model = User
            stream = 'test'
            exclude = ['first_name', 'last_name']

            @classmethod
            def group_names(cls, instance, action):
                return ["users_exclude"]

            def has_permission(self, user, action, pk):
                return True

        with apply_routes([route('test', TestBinding.consumer)]):
            client = HttpClient()
            client.join_group('users_exclude')

            user = User.objects.create(username='test', email='test@test.com')
            consumer_finished.send(sender=None)
            consumer_finished.send(sender=None)
            received = client.receive()

            self.assertTrue('payload' in received)
            self.assertTrue('action' in received['payload'])
            self.assertTrue('data' in received['payload'])
            self.assertTrue('username' in received['payload']['data'])
            self.assertTrue('email' in received['payload']['data'])
            self.assertTrue('password' in received['payload']['data'])
            self.assertTrue('model' in received['payload'])
            self.assertTrue('pk' in received['payload'])

            self.assertFalse('last_name' in received['payload']['data'])
            self.assertFalse('first_name' in received['payload']['data'])

            self.assertEqual(received['payload']['action'], 'create')
            self.assertEqual(received['payload']['model'], 'auth.user')
            self.assertEqual(received['payload']['pk'], user.pk)

            self.assertEqual(received['payload']['data']['email'], 'test@test.com')
            self.assertEqual(received['payload']['data']['username'], 'test')
            self.assertEqual(received['payload']['data']['password'], '')

            received = client.receive()
            self.assertIsNone(received)

    def test_omit_fields_and_exclude(self):
        def _declare_class():
            class TestBinding(WebsocketBinding):
                model = User
                stream = 'test'

                @classmethod
                def group_names(cls, instance, action):
                    return ["users_omit"]

                def has_permission(self, user, action, pk):
                    return True
        self.assertRaises(ValueError, _declare_class)

    def test_trigger_outbound_update(self):
        class TestBinding(WebsocketBinding):
            model = User
            stream = 'test'
            fields = ['__all__']

            @classmethod
            def group_names(cls, instance, action):
                return ["users2"]

            def has_permission(self, user, action, pk):
                return True

        # Make model and clear out pending sends
        user = User.objects.create(username='test', email='test@test.com')
        consumer_finished.send(sender=None)

        client = HttpClient()
        client.join_group('users2')

        user.username = 'test_new'
        user.save()

        consumer_finished.send(sender=None)
        received = client.receive()
        self.assertTrue('payload' in received)
        self.assertTrue('action' in received['payload'])
        self.assertTrue('data' in received['payload'])
        self.assertTrue('username' in received['payload']['data'])
        self.assertTrue('email' in received['payload']['data'])
        self.assertTrue('password' in received['payload']['data'])
        self.assertTrue('last_name' in received['payload']['data'])
        self.assertTrue('model' in received['payload'])
        self.assertTrue('pk' in received['payload'])

        self.assertEqual(received['payload']['action'], 'update')
        self.assertEqual(received['payload']['model'], 'auth.user')
        self.assertEqual(received['payload']['pk'], user.pk)

        self.assertEqual(received['payload']['data']['email'], 'test@test.com')
        self.assertEqual(received['payload']['data']['username'], 'test_new')
        self.assertEqual(received['payload']['data']['password'], '')
        self.assertEqual(received['payload']['data']['last_name'], '')

        received = client.receive()
        self.assertIsNone(received)

    def test_trigger_outbound_delete(self):
        class TestBinding(WebsocketBinding):
            model = User
            stream = 'test'
            fields = ['username']

            @classmethod
            def group_names(cls, instance, action):
                return ["users3"]

            def has_permission(self, user, action, pk):
                return True

        # Make model and clear out pending sends
        user = User.objects.create(username='test', email='test@test.com')
        consumer_finished.send(sender=None)

        client = HttpClient()
        client.join_group('users3')

        user.delete()

        consumer_finished.send(sender=None)
        received = client.receive()
        self.assertTrue('payload' in received)
        self.assertTrue('action' in received['payload'])
        self.assertTrue('data' in received['payload'])
        self.assertTrue('username' in received['payload']['data'])
        self.assertTrue('model' in received['payload'])
        self.assertTrue('pk' in received['payload'])

        self.assertEqual(received['payload']['action'], 'delete')
        self.assertEqual(received['payload']['model'], 'auth.user')
        self.assertEqual(received['payload']['pk'], 1)
        self.assertEqual(received['payload']['data']['username'], 'test')

        received = client.receive()
        self.assertIsNone(received)

    def test_demultiplexer(self):
        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        with apply_routes([Demultiplexer.as_route(path='/')]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')

            # assert in group
            Group('inbound').send({'text': json.dumps({'test': 'yes'})}, immediately=True)
            self.assertEqual(client.receive(), {'test': 'yes'})

            # assert that demultiplexer stream message
            client.send_and_consume('websocket.receive', path='/',
                                    text={'stream': 'users', 'payload': {'test': 'yes'}})
            message = client.get_next_message('binding.users')
            self.assertIsNotNone(message)
            self.assertEqual(message.content['test'], 'yes')

    def test_demultiplexer_with_wrong_stream(self):
        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        with apply_routes([Demultiplexer.as_route(path='/')]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')

            with self.assertRaises(ValueError) as value_error:
                client.send_and_consume('websocket.receive', path='/', text={
                    'stream': 'wrong', 'payload': {'test': 'yes'}
                })

            self.assertIn('stream not mapped', value_error.exception.args[0])

            message = client.get_next_message('binding.users')
            self.assertIsNone(message)

    def test_demultiplexer_with_wrong_payload(self):
        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        with apply_routes([Demultiplexer.as_route(path='/')]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')

            with self.assertRaises(ValueError) as value_error:
                client.send_and_consume('websocket.receive', path='/', text={
                    'stream': 'users', 'payload': 'test',
                })

            self.assertEqual(value_error.exception.args[0], 'Multiplexed frame payload is not a dict')

            message = client.get_next_message('binding.users')
            self.assertIsNone(message)

    def test_demultiplexer_without_payload_and_steam(self):
        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        with apply_routes([Demultiplexer.as_route(path='/')]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')

            with self.assertRaises(ValueError) as value_error:
                client.send_and_consume('websocket.receive', path='/', text={
                    'nostream': 'users', 'payload': 'test',
                })

            self.assertIn('no channel/payload key', value_error.exception.args[0])

            message = client.get_next_message('binding.users')
            self.assertIsNone(message)

            with self.assertRaises(ValueError) as value_error:
                client.send_and_consume('websocket.receive', path='/', text={
                    'stream': 'users',
                })

            self.assertIn('no channel/payload key', value_error.exception.args[0])

            message = client.get_next_message('binding.users')
            self.assertIsNone(message)

    def test_inbound_create(self):
        self.assertEqual(User.objects.all().count(), 0)

        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        class UserBinding(WebsocketBinding):
            model = User
            stream = 'users'
            fields = ['username', 'email', 'password', 'last_name']

            @classmethod
            def group_names(cls, instance, action):
                return ['users_outbound']

            def has_permission(self, user, action, pk):
                return True

        with apply_routes([Demultiplexer.as_route(path='/'), route('binding.users', UserBinding.consumer)]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')
            client.send_and_consume('websocket.receive', path='/', text={
                'stream': 'users',
                'payload': {'action': CREATE, 'data': {'username': 'test_inbound', 'email': 'test@user_steam.com'}}
            })
            # our Demultiplexer route message to the inbound consumer, so call Demultiplexer consumer
            client.consume('binding.users')

        self.assertEqual(User.objects.all().count(), 1)
        user = User.objects.all().first()
        self.assertEqual(user.username, 'test_inbound')
        self.assertEqual(user.email, 'test@user_steam.com')

        self.assertIsNone(client.receive())

    def test_inbound_update(self):
        user = User.objects.create(username='test', email='test@channels.com')

        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        class UserBinding(WebsocketBinding):
            model = User
            stream = 'users'
            fields = ['username', ]

            @classmethod
            def group_names(cls, instance, action):
                return ['users_outbound']

            def has_permission(self, user, action, pk):
                return True

        with apply_routes([Demultiplexer.as_route(path='/'), route('binding.users', UserBinding.consumer)]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')
            client.send_and_consume('websocket.receive', path='/', text={
                'stream': 'users',
                'payload': {'action': UPDATE, 'pk': user.pk, 'data': {'username': 'test_inbound'}}
            })
            # our Demultiplexer route message to the inbound consumer, so call Demultiplexer consumer
            client.consume('binding.users')

            user = User.objects.get(pk=user.pk)
            self.assertEqual(user.username, 'test_inbound')
            self.assertEqual(user.email, 'test@channels.com')

            # trying change field that not in binding fields
            client.send_and_consume('websocket.receive', path='/', text={
                'stream': 'users',
                'payload': {'action': UPDATE, 'pk': user.pk, 'data': {'email': 'new@test.com'}}
            })
            client.consume('binding.users')

            user = User.objects.get(pk=user.pk)
            self.assertEqual(user.username, 'test_inbound')
            self.assertEqual(user.email, 'test@channels.com')

            self.assertIsNone(client.receive())

    def test_inbound_delete(self):
        user = User.objects.create(username='test', email='test@channels.com')

        class Demultiplexer(WebsocketDemultiplexer):
            mapping = {
                'users': 'binding.users',
            }

            groups = ['inbound']

        class UserBinding(WebsocketBinding):
            model = User
            stream = 'users'
            fields = ['username', ]

            @classmethod
            def group_names(cls, instance, action):
                return ['users_outbound']

            def has_permission(self, user, action, pk):
                return True

        with apply_routes([Demultiplexer.as_route(path='/'), route('binding.users', UserBinding.consumer)]):
            client = HttpClient()
            client.send_and_consume('websocket.connect', path='/')
            client.send_and_consume('websocket.receive', path='/', text={
                'stream': 'users',
                'payload': {'action': DELETE, 'pk': user.pk}
            })
            # our Demultiplexer route message to the inbound consumer, so call Demultiplexer consumer
            client.consume('binding.users')

        self.assertIsNone(User.objects.filter(pk=user.pk).first())
        self.assertIsNone(client.receive())
